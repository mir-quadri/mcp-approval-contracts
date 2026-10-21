# Verification record — October 21, 2026

Executed locally with Python 3.12 and official `mcp` SDK 1.30.0.

```text
python -m unittest discover -s tests -v
Ran 9 tests in 3.655s
OK
```

The suite started official FastMCP fixtures on random loopback ports. The safe server passed. Separate deliberately unsafe fixture modes were detected:

- Proposal mutates authoritative assignments.
- Agent-facing approval tool is exposed.
- Proposal is already marked approved.
- Proposal base version differs from the authoritative current version.

Additional validation covers strict JSON pointers, unsafe URL/configuration rejection, and required CLI sandbox acknowledgment.

A separate real HTTP run against an isolated ReadyTogether 0.2.0 local server and temporary SQLite database also passed:

```json
{
  "passed": true,
  "protocol": "2025-11-25",
  "tools_discovered": 4,
  "protected_paths_checked": ["/state/tasks", "/state/packageId"],
  "proposals_checked": 2,
  "checks": [
    "explicit denied tools absent",
    "proposal leaves authoritative fields unchanged",
    "all proposals pending",
    "proposal version matches current state"
  ]
}
```

This is local execution evidence, not a claim that remote CI has passed, that all integrations are safe, or that the public repository has already been published. Exact test duration can vary on another machine.
