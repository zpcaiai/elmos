"""Out-of-band binding for the package's secrets.

Two of them: the evidence seal key (release gate) and the package signing key
(capability package registry). They are separate secrets on purpose - one
attests that a bundle of evidence is intact, the other that a distributed
package is the one that was signed - and a deployment that reused a single key
for both would let anyone who could seal evidence also mint a package.

The capability core deliberately knows nothing about where the key comes from.
``releasegate.set_default_seal_key`` takes bytes and ``default_seal_key`` fails
closed with ``EVIDENCE_UNVERIFIABLE`` when nothing was bound, which is correct
and already tested — but nothing in this package ever called it, so the release
gate was fail-closed *and unusable*: every deployment would have hit
``EVIDENCE_UNVERIFIABLE`` on its first release and had no supported way to fix
it. Fail-closed with no door is not a security posture, it is an outage that
looks like one.

This module is the door, and its shape is the point.

**The key is read from a file, never from an environment variable.** The
variable names a *path*; the secret itself never enters the process
environment. That distinction is not stylistic:

* every child process inherits the environment, so a secret there is handed to
  every subprocess this package spawns — and ``deployment.SubprocessCommandRunner``
  exists precisely to spawn some;
* ``/proc/<pid>/environ`` exposes it to anything running as the same user;
* container runtimes, orchestrators and crash reporters routinely capture and
  ship the environment block, and a core dump contains it verbatim;
* `docker inspect`, `kubectl describe pod` and most CI logs print env values.

A file can be mounted read-only, `0400`, from a secret store, and unmounted.
That is what every secret manager in this deployment's stack already emits.

The key never appears in a return value, a log line, an error message or a
repr. The functions here return the number of bytes bound, not the bytes.
"""

from __future__ import annotations

import os
from pathlib import Path

from elmos_autonomy_kernel.packreg import set_default_signing_key
from elmos_autonomy_kernel.releasegate import set_default_seal_key

from .errors import ContractError

#: Names a path. Never the secret.
SEAL_KEY_PATH_ENV = "ELMOS_AUTONOMY_SEAL_KEY_FILE"

#: The package signing key. A different secret, and a different variable: a
#: deployment that pointed both at one file would let anyone able to seal
#: evidence also mint a package that verifies.
SIGNING_KEY_PATH_ENV = "ELMOS_AUTONOMY_SIGNING_KEY_FILE"

#: Matches the core's ``evidence._MIN_SEAL_KEY_BYTES``. Checked here as well as
#: there so an operator learns at startup rather than on their first release —
#: the core's check fires deep inside a release gate, hours later, in front of
#: whoever was trying to ship.
MIN_SEAL_KEY_BYTES = 32


def _read_key(path: str | os.PathLike[str], *, what: str) -> bytes:
    """Read and validate key material. Returns the bytes; never logs them.

    Trailing whitespace and a single trailing newline are stripped, because
    every way an operator actually creates this file — ``openssl rand -hex 32 >
    key``, a heredoc, a secret store writing a text value — appends one, and a
    key that silently differs from the one the sealing side used produces
    ``BUNDLE_SEAL_INVALID`` on every bundle with no hint as to why. Interior
    bytes are untouched: a binary key is used exactly as written.
    """

    location = Path(path)
    try:
        material = location.read_bytes()
    except OSError as exc:
        # The path is named because an operator needs it to fix this; the
        # contents are not read on the failure path at all.
        raise ContractError(
            "EVIDENCE_UNVERIFIABLE",
            f"cannot read the {what} from {location}: {exc.strerror or exc}",
        ) from exc

    material = material.rstrip(b"\r\n \t")
    if len(material) < MIN_SEAL_KEY_BYTES:
        raise ContractError(
            "EVIDENCE_UNVERIFIABLE",
            f"the {what} at {location} is {len(material)} bytes; "
            f"at least {MIN_SEAL_KEY_BYTES} are required",
        )
    return material


def bind_seal_key_from_file(path: str | os.PathLike[str]) -> int:
    """Bind the evidence seal key from ``path``. Returns the byte count.

    Trailing whitespace and a single trailing newline are stripped, because
    every way an operator actually creates this file - ``openssl rand -hex 32 >
    key``, a heredoc, a secret store writing a text value - appends one, and a
    key that silently differs from the one the sealing side used produces
    ``BUNDLE_SEAL_INVALID`` on every bundle with no hint as to why. Interior
    bytes are untouched: a binary key is used exactly as written.
    """

    material = _read_key(path, what="evidence seal key")
    set_default_seal_key(material)
    return len(material)


def bind_signing_key_from_file(path: str | os.PathLike[str]) -> int:
    """Bind the package signing key from ``path``. Returns the byte count.

    Without it the registry cannot recompute a package's HMAC, so
    ``capability-package-registry`` refuses rather than trusting the signature
    it was handed. That refusal is the point: the legacy path reads the
    caller's own ``signature.valid`` boolean, which is a claim rather than a
    verification, on a supply-chain surface.
    """

    material = _read_key(path, what="package signing key")
    set_default_signing_key(material)
    return len(material)


def bind_signing_key_from_environment(*, required: bool) -> int | None:
    """Bind from the path named by ``ELMOS_AUTONOMY_SIGNING_KEY_FILE``.

    Same required/optional split and same file-not-variable rule as the seal
    key; see ``bind_seal_key_from_environment``.
    """

    raw = os.environ.get(SIGNING_KEY_PATH_ENV, "").strip()
    if not raw:
        if required:
            raise ContractError(
                "SIGNATURE_INVALID",
                f"{SIGNING_KEY_PATH_ENV} is not set; it must name a file containing the "
                f"package signing key ({MIN_SEAL_KEY_BYTES}+ bytes).",
            )
        return None
    return bind_signing_key_from_file(raw)


def bind_seal_key_from_environment(*, required: bool) -> int | None:
    """Bind from the path named by ``ELMOS_AUTONOMY_SEAL_KEY_FILE``.

    ``required`` is an argument rather than a default because the two callers
    want opposite things and neither may get the other's behaviour by accident.
    A server that will evaluate release gates must refuse to start without a
    key — a process that boots and then fails every gate is strictly worse than
    one that does not boot, because the first looks healthy. A one-shot CLI
    dispatch that may never touch the release gate should not be blocked from
    running ``census`` because no key is configured.

    Returns the byte count, or ``None`` when nothing was bound and ``required``
    is false. Never returns the key.
    """

    raw = os.environ.get(SEAL_KEY_PATH_ENV, "").strip()
    if not raw:
        if required:
            raise ContractError(
                "EVIDENCE_UNVERIFIABLE",
                f"{SEAL_KEY_PATH_ENV} is not set; it must name a file containing the "
                f"evidence seal key ({MIN_SEAL_KEY_BYTES}+ bytes). The key is read "
                "from a file rather than from the variable itself so that it is not "
                "inherited by child processes or captured in crash dumps.",
            )
        return None
    return bind_seal_key_from_file(raw)
