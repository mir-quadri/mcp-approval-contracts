# MCP Approval Contracts

**Catch “propose” tools that quietly commit changes.**

A small, MIT-licensed Python library and CLI for executable approval-boundary checks against proposal-only MCP servers. It uses the official MCP Python SDK over **real Streamable HTTP**, negotiates **2025-11-25**, discovers tools, calls an explicitly configured scenario, and inspects authoritative state before and after the proposal.

Built by Mir Quadri during the Amazon Developer Hackathon window on October 21, 2026. This is a separate reusable contribution alongside ReadyTogether, not a copy of the application.

## Why it matters

A tool named `propose_repair` can return reassuring text while mutating the real assignment behind the scenes. A unit test of the planner alone may miss the server wiring. These contracts check the externally observable boundary, including tool exposure and pending proposal state, using the same protocol clients use.

The [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) recommends human oversight with the ability to deny invocations. This harness is an application-specific test of a proposal-only design. MCP does **not** mandate that every tool be proposal-only, and a passing result is **not** an MCP certification or security guarantee.

## Install

Python 3.11+:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Dependency: [`mcp==1.30.0`](https://github.com/modelcontextprotocol/python-sdk), the official SDK. Its dependencies are installed under their own licenses; vendor source is not bundled.

## Try the included synthetic fixture

Terminal 1:

```sh
PORT=8000 FIXTURE_MODE=safe python tests/fixtures/server.py
```

Terminal 2:

```sh
mcp-approval-contracts http://127.0.0.1:8000/mcp examples/fixture.json --confirm-sandbox
```

The report returns `passed: true`, negotiated protocol, discovered-tool count, protected paths, and proposal count. It does not print private state or endpoint credentials. Run the fixture with `FIXTURE_MODE=mutating`, `exposed`, `auto_approved`, or `stale` to see intentional contract failures.

**Only run against a synthetic sandbox you own or are authorized to test.** Setup and proposal tools may change test data. `--confirm-sandbox` is mandatory. Calls are not rolled back, including when a check fails or times out. Non-loopback endpoints additionally require `--allow-remote` and HTTPS. Redirects and environment proxies are disabled for predictable direct endpoint testing. Do not embed credentials in the URL.

## What is checked

1. The server negotiates the exact configured protocol version.
2. Tool discovery is paginated with a bounded page count.
3. Explicitly denied tool names are absent. Names are exact matches, not blanket keyword bans; a tool such as `accept_terms_preview` is not inferred to be dangerous.
4. Required read, proposal, and setup tools exist before any scenario is invoked.
5. The configured protected state fields remain unchanged after the proposal, as reported by the authoritative read tool.
6. At least one proposal exists and every proposal is pending review.
7. Optionally, every proposal's base version matches the current authoritative state version.

An absent field, failed tool, invalid JSON response, missing proposal, or transport failure does not count as passing.

## Configure another server

Copy `examples/fixture.json`. All configured paths use [RFC 6901 JSON pointers](https://www.rfc-editor.org/rfc/rfc6901).

```json
{
  "setup": [],
  "read": {"name": "read_plan"},
  "propose": {"name": "propose_repair", "arguments": {}},
  "protected_paths": ["/state/assignments"],
  "proposals_path": "/state/proposals",
  "denied_tools": ["approve_plan", "accept_assignment"],
  "status_path": "/status",
  "proposal_version_path": "/baseVersion",
  "current_version_path": "/state/version"
}
```

Each tool result must provide `structuredContent` or exactly one JSON text block. `protected_paths` are resolved against read-tool results. `proposals_path` is resolved against the proposal-tool result, and must identify a non-empty array. `status_path` and `proposal_version_path` are relative to each proposal. `current_version_path` is resolved against the post-proposal read result. Omit both version paths to disable that check.

The default protocol is `2025-11-25`; set `expected_protocol` explicitly when testing another version. The default status is `pending`; `pending_status` can override it. Unknown configuration keys and configured calls that match a denied tool are rejected. Use the default 20-second deadline or `--timeout` up to 300 seconds.

## ReadyTogether integration

`examples/ready-together.json` prepares a synthetic cancellation and budget change, reads the event, invokes `propose_coverage_repair`, and verifies that the tasks and selected supply package remain unchanged while proposals await review. It also checks proposal base versions.

With ReadyTogether's local server running:

```sh
mcp-approval-contracts http://127.0.0.1:4173/mcp examples/ready-together.json --confirm-sandbox
```

The application does not need to be made public for local testing. This separate harness repository can be public while the primary application remains private.

## Python API

```python
import asyncio, json
from pathlib import Path
from mcp_approval_contracts import Contract, check_server

contract = Contract.from_dict(json.loads(Path("examples/fixture.json").read_text()))
report = asyncio.run(check_server("http://127.0.0.1:8000/mcp", contract))
print(report["passed"])
```

Calling the Python API is an explicit authorization to run its configured tools; apply your own confirmation flow if exposing it to end users.

## Tests

```sh
python -m unittest discover -s tests -v
```

Nine tests include five actual HTTP client/server scenarios: one safe fixture and four failure modes. Additional checks cover JSON pointer escapes, invalid configuration, remote authorization/TLS, and the CLI's sandbox acknowledgment. The suite uses random local ports and terminates each fixture process.

## Limits

This tests configured observable behavior for a chosen scenario. It cannot prove that a dishonest read tool reports real state, that all side effects were captured, that a browser's approval represents an authenticated human, or that hidden/unlisted execution paths are safe. It does not attempt to call denied approval tools. It does not prove that stale proposals are rejected during later execution; the optional version check only detects mismatched proposal base versions at observation time. It does not establish privacy compliance or accessibility compliance. Add application authorization, transactional concurrency checks, and adversarial tests separately.

## Contribution summary

**What:** A reusable proposal-boundary contract runner with CLI, library, sample configurations, safe and deliberately unsafe MCP fixtures, and regression tests.

**How:** It uses the official SDK to negotiate Streamable HTTP, discover tools, and compare selected authoritative fields across a proposal call while checking review status and version references.

**Why:** It helps developers catch an integration bug that can otherwise make an agent appear to wait for approval while its server has already changed the plan.

GitHub username: `mir-quadri`. Public contribution URL and repository URL must be added after this source is actually published. Do not claim Open Source mini-challenge completion before that publication.
