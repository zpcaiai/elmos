import unittest
from datetime import datetime, timezone
import time
from elmos_mature_platform.job_fairness_tenant_isolation_engine import JobFairnessTenantIsolationEngine
from elmos_mature_platform.types import TenantQuota, FairnessJob, JobQueueStatus, FairnessPolicy

class TestJobFairnessTenantIsolationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = JobFairnessTenantIsolationEngine()
        self.engine.register_tenant(TenantQuota(tenant_id="t1", max_concurrent_jobs=2, max_cpu_cores=10, max_memory_gb=20, priority_weight=1.0))
        self.engine.register_tenant(TenantQuota(tenant_id="t2", max_concurrent_jobs=5, max_cpu_cores=50, max_memory_gb=100, priority_weight=2.0))

    def test_register_tenant(self):
        tid = self.engine.register_tenant(TenantQuota(tenant_id="t3"))
        self.assertEqual(tid, "t3")

    def test_update_quota(self):
        quota = self.engine.update_quota("t1", max_cpu_cores=15)
        self.assertEqual(quota.max_cpu_cores, 15)

    def test_update_quota_not_found(self):
        with self.assertRaises(PermissionError):
            self.engine.update_quota("invalid", max_cpu_cores=15)

    def test_submit_job_valid(self):
        job = FairnessJob(job_id="j1", tenant_id="t1")
        jid = self.engine.submit_job(job)
        self.assertEqual(jid, "j1")
        self.assertEqual(self.engine.jobs["j1"].status, JobQueueStatus.QUEUED)

    def test_submit_job_invalid_tenant(self):
        job = FairnessJob(job_id="j1", tenant_id="invalid")
        with self.assertRaises(PermissionError):
            self.engine.submit_job(job)

    def test_schedule_job_success(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=5))
        job = self.engine.schedule_job("j1")
        self.assertEqual(job.status, JobQueueStatus.RUNNING)
        self.assertEqual(self.engine.tenants["t1"].current_cpu_used, 5)

    def test_schedule_job_throttled_cpu(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=15))
        job = self.engine.schedule_job("j1")
        self.assertEqual(job.status, JobQueueStatus.THROTTLED)

    def test_schedule_job_burst_allowed(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=12))
        job = self.engine.schedule_job("j1", allow_burst=True)
        # max 10 * 1.5 = 15
        self.assertEqual(job.status, JobQueueStatus.RUNNING)

    def test_schedule_job_burst_denied(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=16))
        job = self.engine.schedule_job("j1", allow_burst=True)
        # max 10 * 1.5 = 15
        self.assertEqual(job.status, JobQueueStatus.THROTTLED)

    def test_preempt_job_success(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=5))
        self.engine.schedule_job("j1")
        job = self.engine.preempt_job("j1", "higher_priority")
        self.assertEqual(job.status, JobQueueStatus.PREEMPTED)
        self.assertEqual(job.preempted_by, "higher_priority")
        self.assertEqual(self.engine.tenants["t1"].current_cpu_used, 0)

    def test_preempt_job_invalid_status(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1"))
        with self.assertRaises(ValueError):
            self.engine.preempt_job("j1", "reason")

    def test_complete_job_success(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=5))
        self.engine.schedule_job("j1")
        job = self.engine.complete_job("j1")
        self.assertEqual(job.status, JobQueueStatus.COMPLETED)
        self.assertEqual(self.engine.tenants["t1"].current_cpu_used, 0)
        self.assertTrue(job.completed_at != "")

    def test_complete_job_invalid_status(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1"))
        with self.assertRaises(ValueError):
            self.engine.complete_job("j1")

    def test_get_tenant_utilization(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=5, memory_gb_requested=10))
        self.engine.schedule_job("j1")
        util = self.engine.get_tenant_utilization("t1")
        self.assertEqual(util["cpu_pct"], 50.0)
        self.assertEqual(util["memory_pct"], 50.0)
        self.assertEqual(util["jobs_pct"], 50.0)

    def test_get_tenant_utilization_invalid(self):
        with self.assertRaises(PermissionError):
            self.engine.get_tenant_utilization("invalid")

    def test_fair_schedule_order_equal_share(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1"))
        time.sleep(0.01)
        self.engine.submit_job(FairnessJob(job_id="j2", tenant_id="t1"))
        time.sleep(0.01)
        self.engine.submit_job(FairnessJob(job_id="j3", tenant_id="t2"))
        
        order = self.engine.get_fair_schedule_order(FairnessPolicy.EQUAL_SHARE)
        self.assertEqual(order, ["j1", "j3", "j2"])

    def test_fair_schedule_order_weighted(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1"))
        self.engine.submit_job(FairnessJob(job_id="j3", tenant_id="t2"))
        
        order = self.engine.get_fair_schedule_order(FairnessPolicy.WEIGHTED)
        self.assertEqual(order, ["j3", "j1"])

    def test_fair_schedule_order_priority(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", priority=1))
        self.engine.submit_job(FairnessJob(job_id="j2", tenant_id="t2", priority=10))
        
        order = self.engine.get_fair_schedule_order(FairnessPolicy.PRIORITY_BASED)
        self.assertEqual(order, ["j2", "j1"])

    def test_detect_noisy_neighbor(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=9))
        self.engine.schedule_job("j1")
        noisy = self.engine.detect_noisy_neighbor(threshold_pct=80.0)
        self.assertEqual(len(noisy), 1)
        self.assertEqual(noisy[0]["tenant_id"], "t1")

    def test_detect_noisy_neighbor_none(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=5))
        self.engine.schedule_job("j1")
        noisy = self.engine.detect_noisy_neighbor(threshold_pct=80.0)
        self.assertEqual(len(noisy), 0)

    def test_get_queue_stats(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1"))
        self.engine.submit_job(FairnessJob(job_id="j2", tenant_id="t2"))
        stats = self.engine.get_queue_stats()
        self.assertEqual(stats["queue_depth"], 2)
        self.assertEqual(stats["by_tenant_queue_depth"]["t1"], 1)

    def test_get_fairness_report(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", cpu_requested=5))
        self.engine.schedule_job("j1")
        
        self.engine.submit_job(FairnessJob(job_id="j2", tenant_id="t1", cpu_requested=15))
        self.engine.schedule_job("j2") # throttled
        
        report = self.engine.get_fairness_report()
        self.assertEqual(report["t1"]["jobs_run"], 1)
        self.assertEqual(report["t1"]["violations"], 1)
        self.assertEqual(report["t1"]["throttled_count"], 1)

    def test_schedule_nonexistent_job(self):
        with self.assertRaises(ValueError):
            self.engine.schedule_job("invalid")

    def test_preempt_nonexistent_job(self):
        with self.assertRaises(ValueError):
            self.engine.preempt_job("invalid", "reason")

    def test_complete_nonexistent_job(self):
        with self.assertRaises(ValueError):
            self.engine.complete_job("invalid")

    def test_schedule_job_throttled_concurrent(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1"))
        self.engine.submit_job(FairnessJob(job_id="j2", tenant_id="t1"))
        self.engine.submit_job(FairnessJob(job_id="j3", tenant_id="t1"))
        self.engine.schedule_job("j1")
        self.engine.schedule_job("j2")
        job3 = self.engine.schedule_job("j3")
        self.assertEqual(job3.status, JobQueueStatus.THROTTLED)
        
    def test_schedule_job_throttled_memory(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", memory_gb_requested=25))
        job1 = self.engine.schedule_job("j1")
        self.assertEqual(job1.status, JobQueueStatus.THROTTLED)
        
    def test_schedule_job_throttled_gpu(self):
        # max_gpu_count for t1 is 0 by default
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", gpu_requested=1))
        job1 = self.engine.schedule_job("j1")
        self.assertEqual(job1.status, JobQueueStatus.THROTTLED)
        
    def test_fair_schedule_order_burst_allowed(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1"))
        time.sleep(0.01)
        self.engine.submit_job(FairnessJob(job_id="j2", tenant_id="t1"))
        time.sleep(0.01)
        self.engine.submit_job(FairnessJob(job_id="j3", tenant_id="t2"))
        
        order = self.engine.get_fair_schedule_order(FairnessPolicy.BURST_ALLOWED)
        self.assertEqual(order, ["j1", "j3", "j2"])
        
    def test_detect_noisy_neighbor_gpu(self):
        self.engine.update_quota("t1", max_gpu_count=4)
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1", gpu_requested=4))
        self.engine.schedule_job("j1")
        noisy = self.engine.detect_noisy_neighbor(threshold_pct=80.0)
        self.assertEqual(len(noisy), 1)
        
    def test_get_queue_stats_with_running(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1"))
        self.engine.schedule_job("j1")
        stats = self.engine.get_queue_stats()
        self.assertEqual(stats["queue_depth"], 0)
        self.assertEqual(stats["by_status"][JobQueueStatus.RUNNING], 1)

    def test_get_fairness_report_preempted(self):
        self.engine.submit_job(FairnessJob(job_id="j1", tenant_id="t1"))
        self.engine.schedule_job("j1")
        self.engine.preempt_job("j1", "high_priority")
        report = self.engine.get_fairness_report()
        self.assertEqual(report["t1"]["violations"], 1)
        self.assertEqual(report["t1"]["preempted_count"], 1)

if __name__ == '__main__':
    unittest.main()
