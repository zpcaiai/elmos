from __future__ import annotations

import json
import tempfile
import unittest
import uuid

from elmos_pi_harness.bridges import (
    ClaudeHarnessBridge,
    CodexHarnessBridge,
    MCPHarnessBridge,
)
from elmos_pi_harness.models import (
    AuthoritySnapshot,
    ExecutorIdentity,
    TextContent,
    ToolResult,
)
from elmos_pi_harness.persistence import DurableStore
from elmos_pi_harness.tool_runtime import ToolRegistry, ToolRuntime


class TestHarnessBridges(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="bridge-test-")
        self.store = DurableStore(":memory:", artifact_root=self.temp.name)
        self.tenant = str(uuid.uuid4())
        self.project = str(uuid.uuid4())
        self.task = str(uuid.uuid4())
        self.store.create_task(self.tenant, self.project, "bridge test", idempotency_key="bridge-1", task_id=self.task, actor_id="tester")

        self.store.create_environment(self.tenant, self.task, "local", config={"workspace": self.temp.name})
        self.env_id = self.store._connection.execute("SELECT environment_id FROM execution_environment").fetchone()[0]

        self.snapshot_id = str(uuid.uuid4())
        self.authority = AuthoritySnapshot(
            authority_owner_id=str(uuid.uuid4()),
            environment_id=self.env_id,
            permission_profile_version="v1",
            allowed_capabilities=frozenset({"tool.echo", "tool.read"}),
            denied_capabilities=frozenset({"tool.bad_tool"}),
        )
        self.store.create_authority_snapshot(self.tenant, self.snapshot_id, self.authority)

        self.executor = ExecutorIdentity("exec-1", 0, "reg-1")
        self.store.register_executor(self.tenant, self.env_id, self.executor)

        self.registry = ToolRegistry()

        def echo_handler(inv, policy):
            return ToolResult(
                call_id=inv.call_id,
                items=(TextContent(f"echo: {inv.args.get('msg', '')}"),),
                status="completed",
                metadata={"executed": True},
            )

        self.registry.register("tool.echo", echo_handler, required_capabilities={"tool.echo"})
        self.runtime = ToolRuntime(self.store, self.registry)

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_codex_harness_bridge_jsonrpc(self) -> None:
        bridge = CodexHarnessBridge(
            self.tenant,
            self.task,
            self.env_id,
            self.snapshot_id,
            self.executor,
            self.authority,
            self.runtime,
        )

        # 1. Thread create
        resp_str = bridge.handle_jsonrpc(json.dumps({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "thread.create",
            "params": {"metadata": {"source": "codex-test"}},
        }))
        resp = json.loads(resp_str)
        self.assertEqual(resp["id"], "1")
        self.assertIn("thread_id", resp["result"])
        th_id = resp["result"]["thread_id"]

        # 2. Turn start
        t_resp = json.loads(bridge.handle_jsonrpc(json.dumps({
            "jsonrpc": "2.0",
            "id": "2",
            "method": "turn.start",
            "params": {"thread_id": th_id, "prompt": "run echo"},
        })))
        self.assertEqual(t_resp["result"]["status"], "running")

        # 3. Tool execute (allowed)
        tool_resp = json.loads(bridge.handle_jsonrpc(json.dumps({
            "jsonrpc": "2.0",
            "id": "3",
            "method": "tool.execute",
            "params": {
                "capability": "tool.echo",
                "arguments": {"msg": "hello world"},
                "required_capabilities": ["tool.echo"],
            },
        })))
        self.assertEqual(tool_resp["result"]["status"], "completed")

        # 4. Tool execute (denied by policy)
        denied_resp = json.loads(bridge.handle_jsonrpc(json.dumps({
            "jsonrpc": "2.0",
            "id": "4",
            "method": "tool.execute",
            "params": {
                "capability": "tool.bad_tool",
                "arguments": {},
                "required_capabilities": ["tool.bad_tool"],
            },
        })))
        self.assertIn("error", denied_resp)
        self.assertEqual(denied_resp["error"]["code"], 4003)

    def test_claude_harness_bridge_hooks(self) -> None:
        bridge = ClaudeHarnessBridge(
            self.tenant,
            self.task,
            self.env_id,
            self.snapshot_id,
            self.executor,
            self.authority,
            self.runtime,
        )

        # Allowed tool
        res = bridge.execute_with_hooks("tool.echo", {"msg": "claude"}, ["tool.echo"])
        self.assertEqual(res.status, "completed")
        self.assertEqual(res.items[0].text, "echo: claude")

        # Denied tool
        res_denied = bridge.execute_with_hooks("tool.bad_tool", {}, ["tool.bad_tool"])
        self.assertEqual(res_denied.status, "failed")
        self.assertTrue(res_denied.metadata.get("policy_denied"))

    def test_mcp_harness_bridge_protocol(self) -> None:
        bridge = MCPHarnessBridge(
            self.tenant,
            self.task,
            self.env_id,
            self.snapshot_id,
            self.executor,
            self.authority,
            self.runtime,
        )

        # 1. Initialize
        init_resp = bridge.handle_request({"jsonrpc": "2.0", "id": "m1", "method": "initialize"})
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "elmos-mcp-server")

        # 2. Tools list
        list_resp = bridge.handle_request({"jsonrpc": "2.0", "id": "m2", "method": "tools/list"})
        tools = list_resp["result"]["tools"]
        self.assertTrue(any(t["name"] == "tool.echo" for t in tools))

        # 3. Tools call
        call_resp = bridge.handle_request({
            "jsonrpc": "2.0",
            "id": "m3",
            "method": "tools/call",
            "params": {"name": "tool.echo", "arguments": {"msg": "mcp-call"}},
        })
        self.assertFalse(call_resp["result"]["isError"])
        self.assertEqual(call_resp["result"]["content"][0]["text"], "echo: mcp-call")


if __name__ == "__main__":
    unittest.main()
