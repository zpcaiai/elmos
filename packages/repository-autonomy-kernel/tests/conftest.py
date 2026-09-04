"""Shared fixtures.

Time is injected everywhere so that no test sleeps and every replay is exact.
"""

from __future__ import annotations

import pytest

from elmos_autonomy_kernel.adapters.memory import (
    FixedClock,
    InMemoryArtifactStore,
    InMemoryEventStore,
    InMemoryKeyValueStore,
    InMemoryLeaseStore,
)
from elmos_autonomy_kernel.contracts import Observability


@pytest.fixture()
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture()
def events(clock: FixedClock) -> InMemoryEventStore:
    return InMemoryEventStore(clock)


@pytest.fixture()
def kv() -> InMemoryKeyValueStore:
    return InMemoryKeyValueStore()


@pytest.fixture()
def artifacts() -> InMemoryArtifactStore:
    return InMemoryArtifactStore()


@pytest.fixture()
def leases(clock: FixedClock) -> InMemoryLeaseStore:
    return InMemoryLeaseStore(clock)


@pytest.fixture()
def obs() -> Observability:
    return Observability(
        tenant_id="tenant-a",
        account_id="account-a",
        run_id="run-1",
        step_id="step-1",
        attempt_no=1,
        task_spec_version="1",
        repo_snapshot_sha="sha256:" + "a" * 64,
        workflow_version="2.0.0",
        skill_version="2.0.0",
        workspace_id="ws-1",
        environment_id="env-1",
        permission_profile_id="profile-standard",
        policy_snapshot_hash="sha256:" + "b" * 64,
        fencing_token=1,
    )
