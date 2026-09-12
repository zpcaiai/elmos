from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from .types import FairnessPolicy, JobQueueStatus, TenantQuota, FairnessJob

class JobFairnessTenantIsolationEngine:
    def __init__(self) -> None:
        self.tenants: Dict[str, TenantQuota] = {}
        self.jobs: Dict[str, FairnessJob] = {}

    def register_tenant(self, quota: TenantQuota) -> str:
        """Register a new tenant with resource quotas."""
        self.tenants[quota.tenant_id] = quota
        return quota.tenant_id

    def update_quota(self, tenant_id: str, **kwargs: Any) -> TenantQuota:
        """Update specific quota fields for an existing tenant."""
        if tenant_id not in self.tenants:
            raise PermissionError(f"Tenant {tenant_id} not found")
        quota = self.tenants[tenant_id]
        for k, v in kwargs.items():
            if hasattr(quota, k):
                setattr(quota, k, v)
        return quota

    def submit_job(self, job: FairnessJob) -> str:
        """Submit a new job for a tenant."""
        if job.tenant_id not in self.tenants:
            raise PermissionError(f"Tenant {job.tenant_id} not found")
        job.status = JobQueueStatus.QUEUED
        job.queued_at = datetime.now(timezone.utc).isoformat()
        self.jobs[job.job_id] = job
        return job.job_id

    def schedule_job(self, job_id: str, allow_burst: bool = False) -> FairnessJob:
        """Attempt to schedule a job based on tenant's current capacity."""
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} not found")
            
        job = self.jobs[job_id]
        if job.status not in (JobQueueStatus.QUEUED, JobQueueStatus.THROTTLED):
            return job
            
        if job.tenant_id not in self.tenants:
            raise PermissionError(f"Tenant {job.tenant_id} not found")
            
        quota = self.tenants[job.tenant_id]
        mult = quota.burst_multiplier if allow_burst else 1.0
        
        if (quota.current_running_jobs + 1 > quota.max_concurrent_jobs * mult or
            quota.current_cpu_used + job.cpu_requested > quota.max_cpu_cores * mult or
            quota.current_memory_used + job.memory_gb_requested > quota.max_memory_gb * mult or
            quota.current_gpu_used + job.gpu_requested > quota.max_gpu_count * mult):
            
            job.status = JobQueueStatus.THROTTLED
            return job
            
        quota.current_running_jobs += 1
        quota.current_cpu_used += job.cpu_requested
        quota.current_memory_used += job.memory_gb_requested
        quota.current_gpu_used += job.gpu_requested
        
        job.status = JobQueueStatus.RUNNING
        now = datetime.now(timezone.utc)
        job.started_at = now.isoformat()
        
        if job.queued_at:
            try:
                queued_time = datetime.fromisoformat(job.queued_at)
                job.wait_time_seconds = (now - queued_time).total_seconds()
            except ValueError:
                pass
                
        return job

    def preempt_job(self, job_id: str, reason: str) -> FairnessJob:
        """Preempt running job, free resources"""
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} not found")
        job = self.jobs[job_id]
        if job.status != JobQueueStatus.RUNNING:
            raise ValueError(f"Cannot preempt job {job_id} in status {job.status}")
            
        quota = self.tenants[job.tenant_id]
        quota.current_running_jobs = max(0, quota.current_running_jobs - 1)
        quota.current_cpu_used = max(0, quota.current_cpu_used - job.cpu_requested)
        quota.current_memory_used = max(0, quota.current_memory_used - job.memory_gb_requested)
        quota.current_gpu_used = max(0, quota.current_gpu_used - job.gpu_requested)
        
        job.status = JobQueueStatus.PREEMPTED
        job.preempted_by = reason
        return job

    def complete_job(self, job_id: str) -> FairnessJob:
        """Complete running job, free resources"""
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} not found")
        job = self.jobs[job_id]
        if job.status != JobQueueStatus.RUNNING:
            raise ValueError(f"Cannot complete job {job_id} in status {job.status}")
            
        quota = self.tenants[job.tenant_id]
        quota.current_running_jobs = max(0, quota.current_running_jobs - 1)
        quota.current_cpu_used = max(0, quota.current_cpu_used - job.cpu_requested)
        quota.current_memory_used = max(0, quota.current_memory_used - job.memory_gb_requested)
        quota.current_gpu_used = max(0, quota.current_gpu_used - job.gpu_requested)
        
        job.status = JobQueueStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc).isoformat()
        return job

    def get_tenant_utilization(self, tenant_id: str) -> Dict[str, Any]:
        """Current resource usage vs quota, utilization percentages"""
        if tenant_id not in self.tenants:
            raise PermissionError(f"Tenant {tenant_id} not found")
        quota = self.tenants[tenant_id]
        
        def pct(used: float, max_val: float) -> float:
            return (used / max_val * 100.0) if max_val > 0 else 0.0
            
        return {
            "tenant_id": tenant_id,
            "jobs_pct": pct(quota.current_running_jobs, quota.max_concurrent_jobs),
            "cpu_pct": pct(quota.current_cpu_used, quota.max_cpu_cores),
            "memory_pct": pct(quota.current_memory_used, quota.max_memory_gb),
            "gpu_pct": pct(quota.current_gpu_used, quota.max_gpu_count),
            "current_running_jobs": quota.current_running_jobs,
            "current_cpu_used": quota.current_cpu_used,
            "current_memory_used": quota.current_memory_used,
            "current_gpu_used": quota.current_gpu_used
        }

    def get_fair_schedule_order(self, policy: FairnessPolicy) -> List[str]:
        """Order queued jobs by policy"""
        queued = [j for j in self.jobs.values() if j.status in (JobQueueStatus.QUEUED, JobQueueStatus.THROTTLED)]
        
        if policy in (FairnessPolicy.EQUAL_SHARE, FairnessPolicy.BURST_ALLOWED):
            tenant_jobs: Dict[str, List[FairnessJob]] = {}
            for j in queued:
                tenant_jobs.setdefault(j.tenant_id, []).append(j)
            for t_jobs in tenant_jobs.values():
                t_jobs.sort(key=lambda x: x.queued_at)
                
            ordered = []
            while tenant_jobs:
                to_remove = []
                for t in sorted(tenant_jobs.keys()):
                    ordered.append(tenant_jobs[t].pop(0).job_id)
                    if not tenant_jobs[t]:
                        to_remove.append(t)
                for t in to_remove:
                    del tenant_jobs[t]
            return ordered
            
        elif policy == FairnessPolicy.WEIGHTED:
            queued.sort(key=lambda j: (
                -self.tenants[j.tenant_id].priority_weight if j.tenant_id in self.tenants else 0,
                j.queued_at
            ))
            return [j.job_id for j in queued]
            
        elif policy == FairnessPolicy.PRIORITY_BASED:
            queued.sort(key=lambda j: (-j.priority, j.queued_at))
            return [j.job_id for j in queued]
            
        return [j.job_id for j in queued]

    def detect_noisy_neighbor(self, threshold_pct: float = 80.0) -> List[Dict[str, Any]]:
        """Tenants using > threshold% of any resource"""
        noisy = []
        for t_id in self.tenants:
            util = self.get_tenant_utilization(t_id)
            if (util["jobs_pct"] > threshold_pct or 
                util["cpu_pct"] > threshold_pct or 
                util["memory_pct"] > threshold_pct or 
                (self.tenants[t_id].max_gpu_count > 0 and util["gpu_pct"] > threshold_pct)):
                noisy.append(util)
        return noisy

    def get_queue_stats(self) -> Dict[str, Any]:
        """Queue depth, avg wait time, by status, by tenant"""
        status_counts: Dict[str, int] = {}
        tenant_counts: Dict[str, int] = {}
        wait_times: List[float] = []
        
        for job in self.jobs.values():
            status_counts[job.status] = status_counts.get(job.status, 0) + 1
            if job.tenant_id not in tenant_counts:
                tenant_counts[job.tenant_id] = 0
            
            if job.status in (JobQueueStatus.QUEUED, JobQueueStatus.THROTTLED):
                tenant_counts[job.tenant_id] += 1
                
            if job.wait_time_seconds > 0:
                wait_times.append(job.wait_time_seconds)
                
        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0.0
        
        queue_depth = sum(1 for j in self.jobs.values() if j.status in (JobQueueStatus.QUEUED, JobQueueStatus.THROTTLED))
        
        return {
            "queue_depth": queue_depth,
            "avg_wait_time": avg_wait,
            "by_status": status_counts,
            "by_tenant_queue_depth": tenant_counts
        }

    def get_fairness_report(self) -> Dict[str, Any]:
        """Per-tenant: jobs run, avg wait, resource usage, violations"""
        report = {}
        for t_id, quota in self.tenants.items():
            t_jobs = [j for j in self.jobs.values() if j.tenant_id == t_id]
            run_count = sum(1 for j in t_jobs if j.status in (JobQueueStatus.RUNNING, JobQueueStatus.COMPLETED, JobQueueStatus.PREEMPTED))
            waits = [j.wait_time_seconds for j in t_jobs if j.wait_time_seconds > 0]
            avg_wait = sum(waits) / len(waits) if waits else 0.0
            
            throttled_count = sum(1 for j in t_jobs if j.status == JobQueueStatus.THROTTLED)
            preempted_count = sum(1 for j in t_jobs if j.status == JobQueueStatus.PREEMPTED)
            
            report[t_id] = {
                "jobs_run": run_count,
                "avg_wait_time": avg_wait,
                "current_cpu_used": quota.current_cpu_used,
                "current_memory_used": quota.current_memory_used,
                "violations": throttled_count + preempted_count,
                "throttled_count": throttled_count,
                "preempted_count": preempted_count
            }
        return report
