import unittest
from elmos_mature_platform.types import (
    StatusPageState,
    CommunicationType,
    ServiceStatus,
    StatusCommunication,
    MaintenanceWindow
)
from elmos_mature_platform.customer_status_communication_engine import CustomerStatusCommunicationEngine

class TestCustomerStatusCommunicationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = CustomerStatusCommunicationEngine()

    def test_register_service(self):
        svc = ServiceStatus(service_id="s1", service_name="Service 1")
        self.engine.register_service(svc)
        self.assertIn("s1", self.engine._services)
        self.assertEqual(self.engine._services["s1"].state, StatusPageState.OPERATIONAL)

    def test_update_service_state(self):
        svc = ServiceStatus(service_id="s2", service_name="Service 2")
        self.engine.register_service(svc)
        updated = self.engine.update_service_state("s2", StatusPageState.DEGRADED, "Slow")
        self.assertEqual(updated.state, StatusPageState.DEGRADED)
        self.assertEqual(updated.message, "Slow")

    def test_update_service_state_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.update_service_state("invalid", StatusPageState.DEGRADED, "Slow")

    def test_create_communication(self):
        comm = StatusCommunication(
            comm_id="c1",
            comm_type=CommunicationType.STATUS_UPDATE,
            title="Update",
            body="All good"
        )
        comm_id = self.engine.create_communication(comm)
        self.assertEqual(comm_id, "c1")
        self.assertIn("c1", self.engine._communications)

    def test_create_communication_no_id(self):
        comm = StatusCommunication(
            comm_id="",
            comm_type=CommunicationType.STATUS_UPDATE,
            title="Update",
            body="All good"
        )
        with self.assertRaises(ValueError):
            self.engine.create_communication(comm)

    def test_create_communication_duplicate(self):
        comm = StatusCommunication(
            comm_id="c2",
            comm_type=CommunicationType.STATUS_UPDATE,
            title="Update",
            body="All good"
        )
        self.engine.create_communication(comm)
        with self.assertRaises(ValueError):
            self.engine.create_communication(comm)

    def test_publish_communication(self):
        comm = StatusCommunication(
            comm_id="c3",
            comm_type=CommunicationType.INCIDENT_NOTICE,
            title="Notice",
            body="Issues"
        )
        self.engine.create_communication(comm)
        published = self.engine.publish_communication("c3")
        self.assertTrue(published.published)
        self.assertNotEqual(published.published_at, "")

    def test_publish_communication_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.publish_communication("invalid")

    def test_publish_communication_already_published(self):
        comm = StatusCommunication(
            comm_id="c4",
            comm_type=CommunicationType.INCIDENT_NOTICE,
            title="Notice",
            body="Issues"
        )
        self.engine.create_communication(comm)
        self.engine.publish_communication("c4")
        published2 = self.engine.publish_communication("c4")
        self.assertTrue(published2.published)

    def test_schedule_maintenance(self):
        window = MaintenanceWindow(window_id="w1", title="Maint")
        w_id = self.engine.schedule_maintenance(window)
        self.assertEqual(w_id, "w1")
        self.assertEqual(self.engine._maintenance_windows["w1"].status, "scheduled")

    def test_schedule_maintenance_no_id(self):
        window = MaintenanceWindow(window_id="", title="Maint")
        with self.assertRaises(ValueError):
            self.engine.schedule_maintenance(window)

    def test_schedule_maintenance_duplicate(self):
        window = MaintenanceWindow(window_id="w2", title="Maint")
        self.engine.schedule_maintenance(window)
        with self.assertRaises(ValueError):
            self.engine.schedule_maintenance(window)

    def test_start_maintenance(self):
        self.engine.register_service(ServiceStatus(service_id="s1", service_name="S1"))
        window = MaintenanceWindow(window_id="w3", title="Maint", service_ids=["s1"])
        self.engine.schedule_maintenance(window)
        started = self.engine.start_maintenance("w3")
        self.assertEqual(started.status, "in_progress")
        self.assertEqual(self.engine._services["s1"].state, StatusPageState.MAINTENANCE)

    def test_start_maintenance_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.start_maintenance("invalid")

    def test_start_maintenance_wrong_status(self):
        window = MaintenanceWindow(window_id="w4", title="Maint")
        self.engine.schedule_maintenance(window)
        self.engine.start_maintenance("w4")
        with self.assertRaises(ValueError):
            self.engine.start_maintenance("w4")

    def test_complete_maintenance(self):
        self.engine.register_service(ServiceStatus(service_id="s1", service_name="S1"))
        window = MaintenanceWindow(window_id="w5", title="Maint", service_ids=["s1"])
        self.engine.schedule_maintenance(window)
        self.engine.start_maintenance("w5")
        completed = self.engine.complete_maintenance("w5")
        self.assertEqual(completed.status, "completed")
        self.assertEqual(self.engine._services["s1"].state, StatusPageState.OPERATIONAL)

    def test_complete_maintenance_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.complete_maintenance("invalid")

    def test_complete_maintenance_wrong_status(self):
        window = MaintenanceWindow(window_id="w6", title="Maint")
        self.engine.schedule_maintenance(window)
        with self.assertRaises(ValueError):
            self.engine.complete_maintenance("w6")

    def test_cancel_maintenance(self):
        window = MaintenanceWindow(window_id="w7", title="Maint")
        self.engine.schedule_maintenance(window)
        cancelled = self.engine.cancel_maintenance("w7")
        self.assertEqual(cancelled.status, "cancelled")

    def test_cancel_maintenance_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.cancel_maintenance("invalid")

    def test_cancel_maintenance_wrong_status(self):
        window = MaintenanceWindow(window_id="w8", title="Maint")
        self.engine.schedule_maintenance(window)
        self.engine.start_maintenance("w8")
        with self.assertRaises(ValueError):
            self.engine.cancel_maintenance("w8")

    def test_get_status_page(self):
        self.engine.register_service(ServiceStatus(service_id="s1", service_name="S1"))
        window = MaintenanceWindow(window_id="w9", title="Maint")
        self.engine.schedule_maintenance(window)
        self.engine.start_maintenance("w9")
        status = self.engine.get_status_page()
        self.assertEqual(len(status["services"]), 1)
        self.assertEqual(len(status["active_maintenance"]), 1)

    def test_get_communication_history_all(self):
        comm = StatusCommunication(
            comm_id="c5",
            comm_type=CommunicationType.STATUS_UPDATE,
            title="Update",
            body="All good"
        )
        self.engine.create_communication(comm)
        self.engine.publish_communication("c5")
        history = self.engine.get_communication_history()
        self.assertEqual(len(history), 1)

    def test_get_communication_history_filtered(self):
        comm = StatusCommunication(
            comm_id="c6",
            comm_type=CommunicationType.STATUS_UPDATE,
            title="Update",
            body="All good",
            affected_services=["s1"]
        )
        self.engine.create_communication(comm)
        self.engine.publish_communication("c6")
        history = self.engine.get_communication_history("s1")
        self.assertEqual(len(history), 1)
        history2 = self.engine.get_communication_history("s2")
        self.assertEqual(len(history2), 0)

    def test_get_communication_history_empty(self):
        history = self.engine.get_communication_history()
        self.assertEqual(len(history), 0)

    def test_get_uptime_summary(self):
        self.engine.register_service(ServiceStatus(service_id="s1", service_name="S1"))
        self.engine.update_service_state("s1", StatusPageState.DEGRADED, "Slow")
        self.engine.update_service_state("s1", StatusPageState.OPERATIONAL, "Fixed")
        summary = self.engine.get_uptime_summary()
        self.assertEqual(summary["s1"]["total_events"], 3) # register + 2 updates
        # states: OP, DEGRADED, OP -> 2/3 OP
        self.assertEqual(summary["s1"]["uptime_percentage"], round(200/3, 2))

    def test_get_uptime_summary_empty(self):
        summary = self.engine.get_uptime_summary()
        self.assertEqual(len(summary), 0)

    def test_communication_not_published_in_history(self):
        comm = StatusCommunication(
            comm_id="c7",
            comm_type=CommunicationType.STATUS_UPDATE,
            title="Draft",
            body="Not ready"
        )
        self.engine.create_communication(comm)
        history = self.engine.get_communication_history()
        self.assertEqual(len(history), 0)
        
    def test_communication_history_order(self):
        comm1 = StatusCommunication(
            comm_id="c8",
            comm_type=CommunicationType.STATUS_UPDATE,
            title="Draft",
            body="Not ready"
        )
        self.engine.create_communication(comm1)
        self.engine.publish_communication("c8")
        
        import time
        time.sleep(0.01)
        
        comm2 = StatusCommunication(
            comm_id="c9",
            comm_type=CommunicationType.STATUS_UPDATE,
            title="Draft",
            body="Not ready"
        )
        self.engine.create_communication(comm2)
        self.engine.publish_communication("c9")
        
        history = self.engine.get_communication_history()
        self.assertEqual(history[0].comm_id, "c9")
        self.assertEqual(history[1].comm_id, "c8")

if __name__ == '__main__':
    unittest.main()
