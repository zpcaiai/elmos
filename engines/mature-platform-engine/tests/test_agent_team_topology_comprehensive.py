import unittest
from elmos_mature_platform.types import (
    AgentTeamRole,
    DelegationPolicy,
    TeamAgentStatus,
    TeamAgent,
    TaskDelegation
)
from elmos_mature_platform.agent_team_topology_engine import AgentTeamTopologyEngine

class TestAgentTeamTopologyEngineComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = AgentTeamTopologyEngine()

    def test_register_agent_success(self):
        agent = TeamAgent(agent_id="a1", name="Agent 1", role=AgentTeamRole.EXECUTOR)
        agent_id = self.engine.register_agent(agent)
        self.assertEqual(agent_id, "a1")
        self.assertIn("a1", self.engine.agents)

    def test_register_agent_duplicate(self):
        agent = TeamAgent(agent_id="a1", name="Agent 1", role=AgentTeamRole.EXECUTOR)
        self.engine.register_agent(agent)
        with self.assertRaises(ValueError):
            self.engine.register_agent(agent)

    def test_set_parent_success(self):
        a1 = TeamAgent(agent_id="a1", name="Agent 1", role=AgentTeamRole.SUPERVISOR)
        a2 = TeamAgent(agent_id="a2", name="Agent 2", role=AgentTeamRole.EXECUTOR)
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        self.engine.set_parent("a2", "a1")
        self.assertEqual(self.engine.agents["a2"].parent_agent_id, "a1")

    def test_set_parent_agent_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.set_parent("a1", "p1")

    def test_set_parent_parent_not_found(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR)
        self.engine.register_agent(a1)
        with self.assertRaises(ValueError):
            self.engine.set_parent("a1", "p1")

    def test_set_parent_circular_direct(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.SUPERVISOR)
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.SUPERVISOR)
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        self.engine.set_parent("a1", "a2")
        with self.assertRaises(ValueError):
            self.engine.set_parent("a2", "a1")

    def test_set_parent_circular_indirect(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.SUPERVISOR)
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.SUPERVISOR)
        a3 = TeamAgent(agent_id="a3", name="A3", role=AgentTeamRole.SUPERVISOR)
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        self.engine.register_agent(a3)
        self.engine.set_parent("a2", "a1")
        self.engine.set_parent("a3", "a2")
        with self.assertRaises(ValueError):
            self.engine.set_parent("a1", "a3")

    def test_delegate_task_success(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, max_concurrent_tasks=2)
        self.engine.register_agent(a1)
        delegation = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        d_id = self.engine.delegate_task(delegation)
        self.assertEqual(d_id, "d1")
        self.assertEqual(self.engine.agents["a1"].current_task_count, 1)

    def test_delegate_task_agent_not_found(self):
        delegation = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        with self.assertRaises(ValueError):
            self.engine.delegate_task(delegation)

    def test_delegate_task_agent_offline(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, status=TeamAgentStatus.OFFLINE)
        self.engine.register_agent(a1)
        delegation = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        with self.assertRaises(ValueError):
            self.engine.delegate_task(delegation)

    def test_delegate_task_agent_draining(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, status=TeamAgentStatus.DRAINING)
        self.engine.register_agent(a1)
        delegation = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        with self.assertRaises(ValueError):
            self.engine.delegate_task(delegation)

    def test_delegate_task_agent_max_capacity(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, max_concurrent_tasks=1)
        self.engine.register_agent(a1)
        d1 = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        self.engine.delegate_task(d1)
        d2 = TaskDelegation(delegation_id="d2", task_id="t2", delegated_to="a1", delegated_by="p1")
        with self.assertRaises(ValueError):
            self.engine.delegate_task(d2)

    def test_auto_delegate_round_robin(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, capabilities=["python"])
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.EXECUTOR, capabilities=["python"])
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        d1 = self.engine.auto_delegate("t1", ["python"], DelegationPolicy.ROUND_ROBIN)
        d2 = self.engine.auto_delegate("t2", ["python"], DelegationPolicy.ROUND_ROBIN)
        d3 = self.engine.auto_delegate("t3", ["python"], DelegationPolicy.ROUND_ROBIN)
        self.assertEqual(d1.delegated_to, "a1")
        self.assertEqual(d2.delegated_to, "a2")
        self.assertEqual(d3.delegated_to, "a1")

    def test_auto_delegate_capability_match(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, capabilities=["python", "java", "c++"])
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.EXECUTOR, capabilities=["python"])
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        d1 = self.engine.auto_delegate("t1", ["python"], DelegationPolicy.CAPABILITY_MATCH)
        self.assertEqual(d1.delegated_to, "a2") # more specialized

    def test_auto_delegate_least_loaded(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, capabilities=["python"], max_concurrent_tasks=5)
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.EXECUTOR, capabilities=["python"], max_concurrent_tasks=5)
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        self.engine.delegate_task(TaskDelegation(delegation_id="d0", task_id="t0", delegated_to="a1", delegated_by="p1"))
        d1 = self.engine.auto_delegate("t1", ["python"], DelegationPolicy.LEAST_LOADED)
        self.assertEqual(d1.delegated_to, "a2")

    def test_auto_delegate_priority_based(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, capabilities=["python"], success_rate=0.8)
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.EXECUTOR, capabilities=["python"], success_rate=0.95)
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        d1 = self.engine.auto_delegate("t1", ["python"], DelegationPolicy.PRIORITY_BASED)
        self.assertEqual(d1.delegated_to, "a2")

    def test_auto_delegate_sticky(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, capabilities=["python"])
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.EXECUTOR, capabilities=["python"])
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        self.engine.delegate_task(TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a2", delegated_by="p1", required_capabilities=["python"]))
        d2 = self.engine.auto_delegate("t2", ["python"], DelegationPolicy.STICKY)
        self.assertEqual(d2.delegated_to, "a2")

    def test_auto_delegate_no_agents_available(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, capabilities=["python"], status=TeamAgentStatus.OFFLINE)
        self.engine.register_agent(a1)
        with self.assertRaises(ValueError):
            self.engine.auto_delegate("t1", ["python"], DelegationPolicy.ROUND_ROBIN)

    def test_auto_delegate_no_matching_capabilities(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, capabilities=["java"])
        self.engine.register_agent(a1)
        with self.assertRaises(ValueError):
            self.engine.auto_delegate("t1", ["python"], DelegationPolicy.ROUND_ROBIN)

    def test_complete_task_success(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR)
        self.engine.register_agent(a1)
        d1 = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        self.engine.delegate_task(d1)
        self.engine.complete_task("d1", True)
        self.assertEqual(a1.current_task_count, 0)
        self.assertEqual(a1.total_tasks_completed, 1)
        self.assertEqual(a1.success_rate, 1.0)
        self.assertTrue(d1.success)

    def test_complete_task_failure(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR)
        self.engine.register_agent(a1)
        d1 = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        self.engine.delegate_task(d1)
        self.engine.complete_task("d1", False)
        self.assertEqual(a1.current_task_count, 0)
        self.assertEqual(a1.total_tasks_completed, 1)
        self.assertEqual(a1.success_rate, 0.0)
        self.assertFalse(d1.success)

    def test_complete_task_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.complete_task("unknown_d", True)

    def test_complete_task_already_completed(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR)
        self.engine.register_agent(a1)
        d1 = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        self.engine.delegate_task(d1)
        self.engine.complete_task("d1", True)
        with self.assertRaises(ValueError):
            self.engine.complete_task("d1", True)

    def test_retry_task_success(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, max_concurrent_tasks=5)
        self.engine.register_agent(a1)
        d1 = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1", max_retries=1)
        self.engine.delegate_task(d1)
        self.engine.complete_task("d1", False)
        d2 = self.engine.retry_task("d1")
        self.assertEqual(d2.retry_count, 1)
        self.assertEqual(d2.delegated_to, "a1")

    def test_retry_task_max_retries_exceeded(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR)
        self.engine.register_agent(a1)
        d1 = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1", retry_count=1, max_retries=1)
        self.engine.delegate_task(d1)
        self.engine.complete_task("d1", False)
        with self.assertRaises(ValueError):
            self.engine.retry_task("d1")

    def test_retry_task_cannot_retry_successful(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR)
        self.engine.register_agent(a1)
        d1 = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        self.engine.delegate_task(d1)
        self.engine.complete_task("d1", True)
        with self.assertRaises(ValueError):
            self.engine.retry_task("d1")

    def test_get_agent_hierarchy(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.SUPERVISOR)
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.EXECUTOR, parent_agent_id="a1")
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        h = self.engine.get_agent_hierarchy()
        self.assertEqual(len(h["hierarchy"]), 1)
        self.assertEqual(h["hierarchy"][0]["agent_id"], "a1")
        self.assertEqual(h["hierarchy"][0]["subordinates"][0]["agent_id"], "a2")

    def test_get_team_load(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, max_concurrent_tasks=2)
        self.engine.register_agent(a1)
        self.engine.delegate_task(TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1"))
        load = self.engine.get_team_load()
        self.assertEqual(load["a1"]["current_tasks"], 1)
        self.assertEqual(load["a1"]["max_tasks"], 2)
        self.assertEqual(load["a1"]["utilization_percent"], 50.0)

    def test_drain_agent(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR)
        self.engine.register_agent(a1)
        self.engine.drain_agent("a1")
        self.assertEqual(a1.status, TeamAgentStatus.DRAINING)
        with self.assertRaises(ValueError):
            self.engine.delegate_task(TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1"))

    def test_drain_agent_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.drain_agent("a1")

    def test_get_capability_matrix(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, capabilities=["python", "java"])
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.EXECUTOR, capabilities=["python"])
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        matrix = self.engine.get_capability_matrix()
        self.assertIn("a1", matrix["python"])
        self.assertIn("a2", matrix["python"])
        self.assertIn("a1", matrix["java"])
        self.assertNotIn("a2", matrix["java"])

    def test_get_team_report(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, success_rate=1.0)
        a2 = TeamAgent(agent_id="a2", name="A2", role=AgentTeamRole.SUPERVISOR, success_rate=0.5)
        self.engine.register_agent(a1)
        self.engine.register_agent(a2)
        rep = self.engine.get_team_report()
        self.assertEqual(rep["total_agents"], 2)
        self.assertEqual(rep["by_role"][AgentTeamRole.EXECUTOR], 1)
        self.assertEqual(rep["by_role"][AgentTeamRole.SUPERVISOR], 1)
        self.assertEqual(rep["avg_success_rate"], 0.75)

    def test_auto_delegate_updates_status_busy(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, capabilities=["python"], max_concurrent_tasks=1)
        self.engine.register_agent(a1)
        self.engine.auto_delegate("t1", ["python"], DelegationPolicy.ROUND_ROBIN)
        self.assertEqual(a1.status, TeamAgentStatus.BUSY)

    def test_complete_task_updates_status_idle(self):
        a1 = TeamAgent(agent_id="a1", name="A1", role=AgentTeamRole.EXECUTOR, max_concurrent_tasks=1)
        self.engine.register_agent(a1)
        d1 = TaskDelegation(delegation_id="d1", task_id="t1", delegated_to="a1", delegated_by="p1")
        self.engine.delegate_task(d1)
        self.assertEqual(a1.status, TeamAgentStatus.BUSY)
        self.engine.complete_task("d1", True)
        self.assertEqual(a1.status, TeamAgentStatus.IDLE)
