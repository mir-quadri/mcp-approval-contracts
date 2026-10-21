"""CLI requires explicit acknowledgment before tools are invoked."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from .contracts import Contract, ContractError, check_server

def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify an authorized synthetic MCP server's proposal boundary.")
    parser.add_argument("endpoint")
    parser.add_argument("contract", type=Path)
    parser.add_argument("--confirm-sandbox", action="store_true", help="Required: configured setup/proposal tools may change test data")
    parser.add_argument("--allow-remote", action="store_true", help="Authorize an HTTPS endpoint beyond loopback")
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args(argv)
    if not args.confirm_sandbox:
        parser.error("--confirm-sandbox is required; tool calls can mutate data")
    try:
        raw = args.contract.read_text(encoding="utf-8")
        if len(raw) > 100_000:
            raise ContractError("Contract config is too large")
        contract = Contract.from_dict(json.loads(raw))
        report = asyncio.run(check_server(args.endpoint, contract, allow_remote=args.allow_remote, timeout=args.timeout))
    except Exception as exc:
        # Do not dump server data, URLs, headers, tokens, or exception groups to CI logs.
        message = str(exc) if isinstance(exc, (ContractError, json.JSONDecodeError, OSError)) else "Protocol/transport failure; inspect the authorized server separately"
        print(json.dumps({"passed": False, "error": message}))
        return 1
    print(json.dumps(report, indent=2))
    return 0
if __name__ == "__main__":
    sys.exit(main())
