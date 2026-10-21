"""Deliberately safe/unsafe synthetic servers for black-box contract tests."""
import os
from copy import deepcopy
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
mode = os.environ.get("FIXTURE_MODE", "safe")
state = {"version": 1, "assignments": [{"task": "welcome", "volunteer": "maya"}], "proposals": []}
server = FastMCP("approval-contract-fixture", host="127.0.0.1", port=int(os.environ["PORT"]), stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=["127.0.0.1:*", "localhost:*"], allowed_origins=["http://127.0.0.1:*", "http://localhost:*"]))
@server.tool()
def read_plan() -> dict:
    return {"state": deepcopy(state)}
@server.tool()
def propose_repair() -> dict:
    state["version"] += 1
    state["proposals"] = [{"status": "approved" if mode == "auto_approved" else "pending", "baseVersion": state["version"] - (1 if mode == "stale" else 0), "volunteer": "jordan"}]
    if mode == "mutating":
        state["assignments"][0]["volunteer"] = "jordan"
    return {"state": deepcopy(state)}
if mode == "exposed":
    @server.tool()
    def approve_plan() -> dict:
        return {"approved": True}
if __name__ == "__main__":
    server.run(transport="streamable-http")
