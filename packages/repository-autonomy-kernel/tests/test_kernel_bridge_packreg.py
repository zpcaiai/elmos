"""capability-package-registry: the signature is recomputed, not read.

The legacy path computes ``signature_valid = signature.get("valid") and
signature.get("key_id")`` — the caller's own boolean. A package is signed
because its payload says it is signed. On a supply-chain surface that is the
whole failure: a signature means the verifier recomputed it, and here the claim
is the verdict.
"""

from __future__ import annotations

import pytest

from elmos_autonomy_kernel.packreg import (
    _decode_package,
    default_signing_key,
    set_default_signing_key,
    sign_package,
)
from elmos_repository_autonomy import kernel_bridge
from elmos_repository_autonomy.dispatcher import AutonomyRuntime
from elmos_repository_autonomy.models import Status

SIGNING_KEY = b"S" * 48


@pytest.fixture()
def runtime():
    return AutonomyRuntime()


@pytest.fixture(autouse=True)
def _signing_key():
    set_default_signing_key(SIGNING_KEY)
    yield
    set_default_signing_key(None)


def _signed_package(**over):
    package = {
        "packageId": "acme-tools", "version": "1.2.0",
        "skills": ["repository-census"], "contractsDigest": "sha256:" + "c" * 64,
        "permissions": {"fs": "read"}, "componentPaths": ["src/a.py"],
        "signature": "hmac-sha256:placeholder",
    }
    package.update(over)
    decoded = _decode_package(package)
    package["signature"] = sign_package(decoded.content_digest, default_signing_key())
    return package


def test_a_correctly_signed_package_is_registered(runtime):
    result = runtime.execute("capability-package-registry",
                             {"package": _signed_package()})

    assert "ENGINE:kernel" in result.reasons
    assert result.output["registered_package"]["signature_verified"] is True


def test_a_forged_signature_is_refused_and_not_downgraded(runtime):
    """The legacy engine would have registered it on the caller's say-so."""

    package = _signed_package()
    package["signature"] = "hmac-sha256:" + "0" * 64
    result = runtime.execute("capability-package-registry", {"package": package})

    assert result.error is not None
    assert result.error.code == "SIGNATURE_INVALID"
    assert "ENGINE:legacy" not in result.reasons


def test_a_tampered_package_no_longer_matches_its_signature(runtime):
    """The signature covers the content digest, so editing the package breaks it."""

    package = _signed_package()
    package["skills"] = ["repository-census", "evidence-release-gate"]
    result = runtime.execute("capability-package-registry", {"package": package})

    assert result.error is not None
    assert result.error.code == "SIGNATURE_INVALID"


def test_a_v2_payload_can_never_promote_and_says_it_verified_nothing(runtime):
    """v2 carries {valid, key_id} and no signature material to recompute from.

    Manufacturing one here with the deployment's own key would have the bridge
    sign the caller's package: every verification would pass, and the check
    would certify only that this process trusts itself.
    """

    result = runtime.execute("capability-package-registry", {
        "package_manifest": {"name": "p", "version": "1.0.0"},
        "components": [{"id": "c1", "path": "a.py", "permissions": {}}],
        "signature": {"valid": True, "key_id": "k1"},
        "test_results": [{"status": "PASS"}],
    })

    assert "ENGINE:legacy" in result.reasons
    package = result.output["registered_package"]
    assert package["signature_verified"] is False
    assert package["signature_claimed"] is True
    assert package["state"] == "REGISTERED"  # legacy still registers it
    assert "not recomputed" in package["signature_note"]


def test_no_signing_key_means_no_registry_rather_than_a_bridge_chosen_one(runtime):
    """A registry keyed by a secret the operator never configured verifies nothing."""

    set_default_signing_key(None)
    result = runtime.execute("capability-package-registry",
                             {"package": {
                                 "packageId": "acme-tools", "version": "1.2.0",
                                 "skills": ["repository-census"],
                                 "contractsDigest": "sha256:" + "c" * 64,
                                 "signature": "hmac-sha256:anything"}})

    assert result.error is not None
    assert result.error.code == "REGISTRY_UNCONFIGURED"


def test_the_output_says_the_registry_only_knows_this_call(runtime):
    """An empty requires_action that reads as an all-clear is the shape being removed.

    ``PackageRegistry`` keeps its state in instance dicts with no port behind
    it, so there is no durable registry to bind - that is work in the core, not
    the bridge. A per-call registry still recomputes the signature, parses the
    version, reviews permissions and resolves dependencies. It just has never
    seen another package, and the response says so.
    """

    result = runtime.execute("capability-package-registry",
                             {"package": _signed_package()})
    package = result.output["registered_package"]

    assert package["registryScope"] == "single-call"
    assert package["requiresAction"] == []
    assert "not that nothing is" in package["registryScopeNote"]


def test_an_unapproved_wildcard_permission_is_refused_not_flagged(runtime):
    """A behaviour change worth stating, and the second of its kind.

    Legacy returns a result with ``permission_review.status: FAIL`` and
    ``state: BLOCKED``; the core raises ``PERMISSION_REVIEW_FAILED``. Both
    refuse to register, but only one of them can be read past. A package asking
    for `fs: *` that nobody approved is not a package with a flag on it.

    The review itself is not lost - it travels in the error details, so the
    caller still learns which permissions were denied and why.
    """

    result = runtime.execute("capability-package-registry",
                             {"package": _signed_package(permissions={"fs": "*"})})

    assert result.error is not None
    assert result.error.code == "PERMISSION_REVIEW_FAILED"
    review = result.error.details["permissionReview"]
    assert review["wildcards"] == ["fs"]
    assert review["denied"] == ["fs"]
    assert review["passed"] is False


def test_a_scoped_permission_passes_the_review(runtime):
    """The refusal above must be reachable in both directions."""

    result = runtime.execute("capability-package-registry",
                             {"package": _signed_package(permissions={"fs": "read"})})

    assert result.error is None
    assert result.output["permission_review"]["passed"] is True


def test_an_unsigned_package_stays_with_legacy(runtime):
    outcome = kernel_bridge.serve("capability-package-registry", {
        "package": {"packageId": "p", "version": "1.0.0", "skills": ["x"],
                    "contractsDigest": "sha256:" + "c" * 64},
    })

    assert outcome.served is False
    assert outcome.reasons == ("KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST",)


def test_the_registry_is_not_left_bound_after_a_call(runtime):
    """A leaked registry would carry one caller's packages into the next call."""

    from elmos_autonomy_kernel.errors import KernelError as KernelSideError
    from elmos_autonomy_kernel.packreg import bound_registry

    runtime.execute("capability-package-registry", {"package": _signed_package()})

    with pytest.raises(KernelSideError) as unbound:
        bound_registry()
    assert unbound.value.code == "REGISTRY_UNCONFIGURED"


def test_a_registered_package_reports_blocked_status_consistently(runtime):
    """Status must not read as validated when the package was refused."""

    package = _signed_package()
    package["signature"] = "hmac-sha256:" + "1" * 64
    result = runtime.execute("capability-package-registry", {"package": package})

    assert result.status == Status.BLOCKED
