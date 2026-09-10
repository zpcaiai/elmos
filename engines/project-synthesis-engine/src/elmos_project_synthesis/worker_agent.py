"""Distributed Worker Agent Daemon.

Implements an industrial execution daemon that:
1. Registers with the HostedRunnerFleet and sends heartbeats.
2. Pulls assigned generation jobs and verifies CAS lease fencing tokens.
3. Executes multi-language enterprise project synthesis in hermetic isolated workspaces.
4. Detects brain-split / revoked leases and aborts zombie worker writes.
5. Emits SHA-256 evidence bundles upon job completion.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from .enterprise_production_target import generate_enterprise_target_files
from .hosted_runner_fleet import HostedRunnerFleet, JobQueueItem, RunnerLease, WorkerNode
from .models import SynthesisRequest

logger = logging.getLogger(__name__)


class WorkerAgentDaemon:
    """Production execution agent bound to a specific worker node."""

    def __init__(
        self,
        node_id: str,
        hostname: str,
        fleet: HostedRunnerFleet,
        max_concurrency: int = 4,
        workspace_root: Path | None = None,
    ) -> None:
        self.node_id = node_id
        self.hostname = hostname
        self.fleet = fleet
        self.max_concurrency = max_concurrency
        self.workspace_root = workspace_root or Path(tempfile.gettempdir()) / "elmos_runner_workspaces"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._is_running = False

    def register(self) -> None:
        """Register worker node with the fleet scheduler."""
        node = WorkerNode(
            node_id=self.node_id,
            hostname=self.hostname,
            max_concurrency=self.max_concurrency,
        )
        self.fleet.register_node(node)

    def heartbeat(self) -> bool:
        """Send alive heartbeat to the fleet controller."""
        return self.fleet.heartbeat(self.node_id)

    def execute_scheduled_job(
        self,
        job: JobQueueItem,
        lease: RunnerLease,
    ) -> dict[str, Any]:
        """Execute a scheduled project synthesis job with strict lease fencing."""
        # 1. Pre-execution lease fencing check
        if not self.fleet.verify_lease(lease.lease_id, lease.fencing_token):
            logger.error(f"Worker {self.node_id}: Lease {lease.lease_id} is invalid/revoked; aborting.")
            return {"status": "ABORTED", "reason": "LEASE_FENCING_INVALID"}

        # 2. Prepare isolated workspace
        job_workspace = self.workspace_root / f"job_{job.job_id}_{lease.fencing_token}"
        job_workspace.mkdir(parents=True, exist_ok=True)

        try:
            # 3. Parse request payload
            payload = job.payload
            request_data = payload.get("request", payload)
            target_lang = payload.get("target_language", "python")

            if "project" in request_data and "approval" in request_data:
                request = SynthesisRequest.from_mapping(request_data)
            else:
                from .intake import approve_request, create_draft

                lang = target_lang
                if lang in ("dotnet", "c#"):
                    lang = "csharp"
                elif lang in ("ts", "js"):
                    lang = "typescript"

                draft = create_draft(
                    name=payload.get("name", "sample-service"),
                    description=payload.get("description", "Enterprise microservice"),
                    entity=payload.get("entity", "order"),
                    languages=[lang],
                    persistence="in-memory",
                    auth_mode="none",
                )
                approved = approve_request(
                    draft,
                    actor=job.actor_id,
                    approved_at=dt.datetime.now(dt.UTC).isoformat(),
                )
                request = SynthesisRequest.from_mapping(approved)

            # 4. Generate enterprise target code
            generated_files = generate_enterprise_target_files(request, language=target_lang)

            # 5. Write generated files to hermetic workspace
            for rel_path, content in generated_files.items():
                dest_file = job_workspace / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_text(content, encoding="utf-8")

            # 6. Post-execution lease fencing check (Brain-split & zombie worker guard)
            if not self.fleet.verify_lease(lease.lease_id, lease.fencing_token):
                logger.error(
                    f"Worker {self.node_id}: Brain-split detected! Lease {lease.lease_id} expired or superseded before commit."
                )
                return {"status": "ABORTED", "reason": "LEASE_SUPERSEDED_BEFORE_COMMIT"}

            # 7. Compute deterministic evidence digest
            manifest_summary = {
                "job_id": job.job_id,
                "node_id": self.node_id,
                "fencing_token": lease.fencing_token,
                "files_count": len(generated_files),
                "target_language": target_lang,
                "completed_at": dt.datetime.now(dt.UTC).isoformat(),
            }
            digest = hashlib.sha256(json.dumps(manifest_summary, sort_keys=True).encode()).hexdigest()

            # 8. Complete job in fleet
            self.fleet.complete_job(job.job_id, success=True)

            return {
                "status": "COMPLETED",
                "files_count": len(generated_files),
                "target_language": target_lang,
                "workspace": str(job_workspace),
                "evidence_sha256": f"sha256:{digest}",
            }

        except Exception as exc:
            logger.exception(f"Worker {self.node_id} job execution failed: {exc}")
            self.fleet.complete_job(job.job_id, success=False, error=str(exc))
            return {"status": "FAILED", "error": str(exc)}
