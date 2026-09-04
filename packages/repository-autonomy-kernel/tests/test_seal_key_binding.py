"""The evidence seal key must be bindable, and bound from the right place.

The kernel already failed closed with EVIDENCE_UNVERIFIABLE when no key was
bound, and that behaviour has a test. What it did not have was a *door*: nothing
in this package ever called ``set_default_seal_key``, so a real deployment was
fail-closed and unusable — every release gate would have returned
EVIDENCE_UNVERIFIABLE with no supported way to configure one. Fail-closed with
no door is an outage that looks like a security posture.
"""

from __future__ import annotations

import pytest

from elmos_autonomy_kernel.errors import KernelError as KernelSideError
from elmos_autonomy_kernel.releasegate import default_seal_key, set_default_seal_key
from elmos_repository_autonomy.errors import ContractError
from elmos_repository_autonomy.seal_key import (
    MIN_SEAL_KEY_BYTES,
    SEAL_KEY_PATH_ENV,
    bind_seal_key_from_environment,
    bind_seal_key_from_file,
)

KEY = b"k" * 48


@pytest.fixture(autouse=True)
def _unbound():
    set_default_seal_key(None)
    yield
    set_default_seal_key(None)


@pytest.fixture()
def key_file(tmp_path):
    path = tmp_path / "seal.key"
    path.write_bytes(KEY)
    return path


def test_a_key_file_binds_and_the_kernel_can_use_it(key_file):
    assert bind_seal_key_from_file(key_file) == len(KEY)
    assert default_seal_key() == KEY


def test_a_trailing_newline_does_not_change_the_key(tmp_path):
    """Every way an operator makes this file appends one.

    ``openssl rand -hex 32 > key`` and a secret store writing a text value both
    add a newline. A key that silently differs from the sealing side's produces
    BUNDLE_SEAL_INVALID on every bundle with nothing pointing at the cause.
    """

    path = tmp_path / "seal.key"
    path.write_bytes(KEY + b"\n")
    assert bind_seal_key_from_file(path) == len(KEY)
    assert default_seal_key() == KEY


def test_interior_bytes_are_untouched(tmp_path):
    """A binary key is used exactly as written; only the trailing edge is trimmed."""

    binary = bytes(range(1, 49))
    path = tmp_path / "seal.key"
    path.write_bytes(binary)
    bind_seal_key_from_file(path)
    assert default_seal_key() == binary


def test_a_short_key_is_refused_at_bind_time_not_at_first_release(tmp_path):
    """The kernel checks length too, but that check fires inside a release gate.

    An operator learning at startup can fix it before anyone tries to ship; one
    learning at the gate finds out in front of whoever was shipping.
    """

    path = tmp_path / "seal.key"
    path.write_bytes(b"a" * (MIN_SEAL_KEY_BYTES - 1))
    with pytest.raises(ContractError) as caught:
        bind_seal_key_from_file(path)
    assert caught.value.info.code == "EVIDENCE_UNVERIFIABLE"
    # And nothing was left bound: a refused bind must not half-apply.
    with pytest.raises(KernelSideError) as unbound:
        default_seal_key()
    assert unbound.value.code == "EVIDENCE_UNVERIFIABLE"


def test_a_missing_file_names_the_path_and_not_the_contents(tmp_path):
    with pytest.raises(ContractError) as caught:
        bind_seal_key_from_file(tmp_path / "absent.key")
    assert caught.value.info.code == "EVIDENCE_UNVERIFIABLE"
    assert "absent.key" in caught.value.info.details["message"]


def test_the_variable_names_a_path_and_never_carries_the_secret(monkeypatch, key_file):
    """The distinction is the whole design, so it is pinned.

    A secret in the environment is inherited by every child process this package
    spawns - ``deployment.SubprocessCommandRunner`` exists to spawn some - is
    readable at /proc/<pid>/environ by anything running as the same user, and is
    captured verbatim in core dumps, `kubectl describe pod` and most CI logs.
    """

    monkeypatch.setenv(SEAL_KEY_PATH_ENV, str(key_file))
    assert bind_seal_key_from_environment(required=True) == len(KEY)
    assert default_seal_key() == KEY

    # Handing the key itself to the variable must fail, not silently work.
    monkeypatch.setenv(SEAL_KEY_PATH_ENV, KEY.decode())
    set_default_seal_key(None)
    with pytest.raises(ContractError):
        bind_seal_key_from_environment(required=True)


def test_required_and_optional_are_opposite_and_neither_is_a_default(monkeypatch):
    """A server must refuse to start; a one-shot census must not be blocked.

    A process that boots and then fails every gate is worse than one that does
    not boot, because the first looks healthy and the failure reads as a
    property of the bundles being submitted.
    """

    monkeypatch.delenv(SEAL_KEY_PATH_ENV, raising=False)

    with pytest.raises(ContractError) as caught:
        bind_seal_key_from_environment(required=True)
    assert caught.value.info.code == "EVIDENCE_UNVERIFIABLE"

    assert bind_seal_key_from_environment(required=False) is None


def test_binding_never_returns_or_prints_the_key(key_file, capsys):
    """The functions return a byte count. The key must not reach any output."""

    count = bind_seal_key_from_file(key_file)
    assert count == len(KEY)
    assert not isinstance(count, (bytes, bytearray))
    captured = capsys.readouterr()
    assert KEY.decode() not in captured.out
    assert KEY.decode() not in captured.err
