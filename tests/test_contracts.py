import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from mcp_approval_contracts import Contract, ContractError, check_server
from mcp_approval_contracts.contracts import pointer, validate_url
ROOT = Path(__file__).resolve().parents[1]
class ContractTests(unittest.TestCase):
    def run_fixture(self, mode):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port=sock.getsockname()[1]
        process=subprocess.Popen([sys.executable, str(ROOT/"tests/fixtures/server.py")], env={**os.environ, "PORT": str(port), "FIXTURE_MODE": mode}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if process.poll() is not None:self.fail("Fixture exited")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.1):break
                except OSError:time.sleep(.03)
            contract=Contract.from_dict(json.loads((ROOT/"examples/fixture.json").read_text()))
            return asyncio.run(check_server(f"http://127.0.0.1:{port}/mcp", contract))
        finally:
            process.terminate();process.wait(timeout=5)
    def test_safe_server_passes_over_real_http(self):
        report=self.run_fixture("safe");self.assertTrue(report["passed"]);self.assertEqual(report["protocol"], "2025-11-25")
    def test_mutating_proposal_is_detected(self):
        with self.assertRaises(ContractError) as ctx:self.run_fixture("mutating")
        self.assertIn("protected state", repr(ctx.exception))
    def test_exposed_approval_tool_is_detected(self):
        with self.assertRaises(ContractError) as ctx:self.run_fixture("exposed")
        self.assertIn("Denied tool exposed", repr(ctx.exception))
    def test_auto_approved_result_is_detected(self):
        with self.assertRaises(ContractError) as ctx:self.run_fixture("auto_approved")
        self.assertIn("not pending", repr(ctx.exception))
    def test_stale_base_version_is_detected(self):
        with self.assertRaises(ContractError) as ctx:self.run_fixture("stale")
        self.assertIn("base version", repr(ctx.exception))
    def test_json_pointer_escapes_and_arrays(self):
        self.assertEqual(pointer({"a/b": [{"x~y": 4}]}, "/a~1b/0/x~0y"),4)
        for path in ("/missing", "/a~2b", "/a~1b/01"):
            with self.assertRaises(ContractError):pointer({"a/b":[]},path)
    def test_remote_requires_authorization_and_tls(self):
        with self.assertRaises(ContractError):validate_url("https://example.com/mcp")
        with self.assertRaises(ContractError):validate_url("http://example.com/mcp",True)
        with self.assertRaises(ContractError):validate_url("https://secret@example.com/mcp",True)
        validate_url("https://example.com/mcp",True)
    def test_config_does_not_allow_denied_call_or_unknown_fields(self):
        data=json.loads((ROOT/"examples/fixture.json").read_text());data["propose"]={"name":"approve_plan"}
        with self.assertRaises(ContractError):Contract.from_dict(data)
        data=json.loads((ROOT/"examples/fixture.json").read_text());data["run_shell"]="echo bad"
        with self.assertRaises(ContractError):Contract.from_dict(data)
    def test_cli_requires_sandbox_acknowledgment(self):
        p=subprocess.run([sys.executable,"-m","mcp_approval_contracts","http://127.0.0.1:1/mcp",str(ROOT/"examples/fixture.json")],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,2);self.assertIn("confirm-sandbox",p.stderr)
if __name__ == "__main__":unittest.main()
