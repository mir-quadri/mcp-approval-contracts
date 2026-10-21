"""Use the official MCP client against an authorized synthetic test endpoint."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
import ipaddress
import json
from typing import Any
from urllib.parse import urlsplit
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

class ContractError(ValueError):
    """Invalid configuration or a failed observable boundary."""

def pointer(document: Any, path: str) -> Any:
    """Resolve a strict RFC 6901 JSON pointer, failing closed on missing data."""
    if path == "":
        return document
    if not path.startswith("/"):
        raise ContractError("JSON pointer must be empty or start with /")
    value = document
    for raw in path[1:].split("/"):
        import re
        if re.search(r"~(?![01])", raw):
            raise ContractError("Invalid JSON pointer escape")
        key = raw.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(value, list):
                if not key.isdigit() or (len(key) > 1 and key.startswith("0")):
                    raise KeyError(key)
                value = value[int(key)]
            elif isinstance(value, dict):
                value = value[key]
            else:
                raise KeyError(key)
        except (KeyError, IndexError, TypeError):
            raise ContractError(f"JSON pointer not found: {path}") from None
    return value

@dataclass(frozen=True)
class Call:
    name: str
    arguments: dict
    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - {"name", "arguments"}:
            raise ContractError("Calls accept only name and arguments")
        if not isinstance(value.get("name"), str) or not value["name"]:
            raise ContractError("Tool name is required")
        if not isinstance(value.get("arguments", {}), dict):
            raise ContractError("Tool arguments must be an object")
        return cls(value["name"], value.get("arguments", {}))

@dataclass(frozen=True)
class Contract:
    read: Call
    propose: Call
    protected_paths: tuple[str, ...]
    proposals_path: str
    denied_tools: tuple[str, ...]
    setup: tuple[Call, ...] = ()
    expected_protocol: str = "2025-11-25"
    pending_status: str = "pending"
    status_path: str = "/status"
    proposal_version_path: str | None = None
    current_version_path: str | None = None

    @classmethod
    def from_dict(cls, data):
        allowed = {"read", "propose", "protected_paths", "proposals_path", "denied_tools", "setup", "expected_protocol", "pending_status", "status_path", "proposal_version_path", "current_version_path"}
        if not isinstance(data, dict) or set(data) - allowed:
            raise ContractError("Unknown contract configuration key")
        required = {"read", "propose", "protected_paths", "proposals_path", "denied_tools"}
        if required - set(data):
            raise ContractError("Missing required contract configuration")
        for key in ("protected_paths", "denied_tools"):
            if not isinstance(data[key], list) or not data[key] or not all(isinstance(x, str) and x for x in data[key]):
                raise ContractError(f"{key} must be a non-empty string array")
        if not isinstance(data.get("setup", []), list) or len(data.get("setup", [])) > 20:
            raise ContractError("setup must be an array of at most 20 calls")
        strings = {k: data.get(k, default) for k, default in [("proposals_path", None), ("expected_protocol", "2025-11-25"), ("pending_status", "pending"), ("status_path", "/status")]}
        if not all(isinstance(v, str) and v for v in strings.values()):
            raise ContractError("Protocol, status, and proposal path must be non-empty strings")
        paths = [*data["protected_paths"], strings["proposals_path"], strings["status_path"]]
        for key in ("proposal_version_path", "current_version_path"):
            if data.get(key) is not None:
                if not isinstance(data[key], str):
                    raise ContractError("Version paths must be strings")
                paths.append(data[key])
        if any(not p.startswith("/") for p in paths):
            raise ContractError("Configured paths must be absolute JSON pointers")
        if bool(data.get("proposal_version_path")) != bool(data.get("current_version_path")):
            raise ContractError("Configure both version paths or neither")
        calls = [Call.parse(data["read"]), Call.parse(data["propose"]), *[Call.parse(c) for c in data.get("setup", [])]]
        if any(c.name in data["denied_tools"] for c in calls):
            raise ContractError("A configured call is explicitly denied")
        return cls(read=calls[0], propose=calls[1], setup=tuple(calls[2:]), protected_paths=tuple(data["protected_paths"]), denied_tools=tuple(data["denied_tools"]), proposals_path=strings["proposals_path"], expected_protocol=strings["expected_protocol"], pending_status=strings["pending_status"], status_path=strings["status_path"], proposal_version_path=data.get("proposal_version_path"), current_version_path=data.get("current_version_path"))

def validate_url(url: str, allow_remote: bool = False):
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ContractError("Use an HTTP(S) endpoint without embedded credentials or fragments")
    host = parsed.hostname
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == "localhost"
    if not local and not allow_remote:
        raise ContractError("Non-loopback endpoints require explicit --allow-remote authorization")
    if not local and parsed.scheme != "https":
        raise ContractError("Remote endpoints require HTTPS")

def unpack(result):
    if result.isError:
        raise ContractError("Configured tool returned isError; no state is included in this report")
    if result.structuredContent is not None:
        return result.structuredContent
    text = [c.text for c in result.content if c.type == "text"]
    if len(text) != 1:
        raise ContractError("Expected structuredContent or exactly one JSON text block")
    try:
        return json.loads(text[0])
    except json.JSONDecodeError:
        raise ContractError("Tool output is not JSON") from None

async def check_server(url: str, contract: Contract, *, allow_remote=False, timeout=20.0) -> dict:
    """Call only configured tools. setup/propose may mutate a synthetic sandbox."""
    validate_url(url, allow_remote)
    if timeout <= 0 or timeout > 300:
        raise ContractError("Timeout must be greater than zero and at most 300 seconds")
    async def execute():
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=timeout) as client, streamable_http_client(url, http_client=client) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                init = await session.initialize()
                if init.protocolVersion != contract.expected_protocol:
                    raise ContractError(f"Expected protocol {contract.expected_protocol}; negotiated {init.protocolVersion}")
                names = set()
                cursor = None
                seen = set()
                for _ in range(30):
                    page = await session.list_tools(cursor=cursor)
                    names.update(t.name for t in page.tools)
                    cursor = page.nextCursor
                    if not cursor:
                        break
                    if cursor in seen:
                        raise ContractError("Tool pagination repeated a cursor")
                    seen.add(cursor)
                else:
                    raise ContractError("Tool discovery exceeded 30 pages")
                denied = sorted(names.intersection(contract.denied_tools))
                if denied:
                    raise ContractError("Denied tool exposed: " + ", ".join(denied))
                for call in (contract.read, contract.propose, *contract.setup):
                    if call.name not in names:
                        raise ContractError(f"Configured tool missing: {call.name}")
                async def invoke(call):
                    return unpack(await session.call_tool(call.name, call.arguments))
                for call in contract.setup:
                    await invoke(call)
                before = await invoke(contract.read)
                protected_before = [pointer(before, p) for p in contract.protected_paths]
                proposal_result = await invoke(contract.propose)
                after = await invoke(contract.read)
                for path, original in zip(contract.protected_paths, protected_before):
                    if pointer(after, path) != original:
                        raise ContractError(f"Proposal changed authoritative protected state: {path}")
                proposals = pointer(proposal_result, contract.proposals_path)
                if not isinstance(proposals, list) or not proposals:
                    raise ContractError("Expected a non-empty proposals array; choose a feasible test scenario")
                for proposal in proposals:
                    if pointer(proposal, contract.status_path) != contract.pending_status:
                        raise ContractError("Proposal was not pending human review")
                    if contract.proposal_version_path:
                        if pointer(proposal, contract.proposal_version_path) != pointer(after, contract.current_version_path):
                            raise ContractError("Proposal base version differs from authoritative current version")
                return {"passed": True, "protocol": init.protocolVersion, "tools_discovered": len(names), "protected_paths_checked": list(contract.protected_paths), "proposals_checked": len(proposals), "checks": ["explicit denied tools absent", "proposal leaves authoritative fields unchanged", "all proposals pending", *( ["proposal version matches current state"] if contract.proposal_version_path else [])], "limitations": "Checks observable configured fields only; not a security certification or proof of authenticated human approval."}
    try:
        async with asyncio.timeout(timeout):
            return await execute()
    except TimeoutError:
        raise ContractError("Contract timed out; do not assume tool calls were cancelled or rolled back") from None
    except ExceptionGroup as group:
        def find_contract_error(exc):
            if isinstance(exc, ContractError):
                return exc
            if isinstance(exc, ExceptionGroup):
                for nested in exc.exceptions:
                    found = find_contract_error(nested)
                    if found:
                        return found
            return None
        failure = find_contract_error(group)
        if failure:
            raise failure from None
        raise
