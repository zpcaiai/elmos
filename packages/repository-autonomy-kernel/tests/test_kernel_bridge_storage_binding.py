"""The kernel path must not trade durable, tenant-scoped storage for depth.

``artifact-evidence-protocol`` is the one bridged skill where the two engines
were each better at a different half of the job.  The kernel's *binding* is far
stronger - evidence names the exact input digests it was produced from, so
evidence about snapshot A cannot justify a claim about snapshot B.  Its
*storage*, though, defaults to a process-local, un-tenanted dictionary: routing
the skill to it naively would have meant the bytes did not survive the request
and one tenant could read another's artifact.

The bridge binds a durable, tenant-scoped store around the kernel call.  These
tests are what stop that binding from being quietly removed later.
"""

from __future__ import annotations

import pytest

from elmos_autonomy_kernel import evidence as kernel_evidence
from elmos_autonomy_kernel.errors import KernelError as CoreKernelError
from elmos_repository_autonomy.dispatcher import AutonomyRuntime, DispatchContext
from elmos_repository_autonomy.storage import DurableStore

pytest.importorskip("elmos_repository_autonomy.kernel_store_adapter")

from test_kernel_bridge_evidence import (  # noqa: E402
    SEAL_KEY,
    artifact_payload,
)

from elmos_autonomy_kernel.releasegate import set_default_seal_key  # noqa: E402
from elmos_repository_autonomy.kernel_store_adapter import (  # noqa: E402
    DurableStoreArtifactStore,
)


@pytest.fixture(autouse=True)
def _seal():
    set_default_seal_key(SEAL_KEY)
    yield
    set_default_seal_key(None)


def _run(store: DurableStore, tenant: str):
    runtime = AutonomyRuntime(store)
    return runtime.execute(
        "artifact-evidence-protocol",
        artifact_payload(),
        context=DispatchContext(tenant_id=tenant, account_id=tenant, store=store),
    )


def test_a_kernel_artifact_lands_in_the_durable_store():
    """The bytes outlive the call, which a process dictionary would not give."""

    store = DurableStore()
    result = _run(store, "tenant-a")

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons

    bound = DurableStoreArtifactStore(store, tenant_id="tenant-a")
    stored_digest = result.output["artifact"]["digest"]
    assert bound.exists(stored_digest) is True
    assert bound.get(stored_digest)  # re-verified against its own content address


def test_one_tenants_artifact_is_not_readable_by_another():
    """Tenant isolation is the property an un-tenanted default store silently loses."""

    store = DurableStore()
    result = _run(store, "tenant-a")
    stored_digest = result.output["artifact"]["digest"]

    other = DurableStoreArtifactStore(store, tenant_id="tenant-b")
    assert other.exists(stored_digest) is False
    with pytest.raises(CoreKernelError) as excinfo:
        other.get(stored_digest)
    assert excinfo.value.code == "EVIDENCE_MISSING"


def test_the_binding_is_restored_even_when_the_kernel_raises():
    """A leaked binding would leave one tenant's store as the process default.

    That is the opposite of what the binding is for, so the restore has to hold
    on the exception path, not just the happy one.
    """

    before = kernel_evidence.default_artifact_store()
    store = DurableStore()
    runtime = AutonomyRuntime(store)

    broken = artifact_payload()
    broken["content"] = {"unreadable": object()}
    result = runtime.execute(
        "artifact-evidence-protocol", broken,
        context=DispatchContext(tenant_id="tenant-a", account_id="tenant-a", store=store),
    )

    assert result.error is not None
    assert kernel_evidence.default_artifact_store() is before


def test_without_a_store_the_kernel_still_answers_and_says_nothing_persisted():
    """No durable store in context is a smaller answer, not a wrong one."""

    runtime = AutonomyRuntime()
    result = runtime.execute("artifact-evidence-protocol", artifact_payload())
    assert result.error is None
    assert result.side_effects_performed is False
