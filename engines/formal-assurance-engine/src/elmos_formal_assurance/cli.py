from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from .artifact_store import AesGcmEnvelopeCipher
from .bundles import HmacEvidenceBundleSigner
from .contracts import TrustedIdentity
from .execution import (
    ExecutionContractError,
    ExecutionPermitSigner,
    load_toolchain_registry,
)
from .runtime import FormalAssuranceRuntime, RuntimeConfig
from .store import StateStore


def _read_private_key(
    path: Path,
    *,
    purpose: str,
    exact_size: int | None = None,
) -> bytes:
    """Read one deployment secret without following links or accepting races."""
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path.expanduser(), flags)
    except OSError as exc:
        raise ExecutionContractError(f"{purpose} key path is unsafe") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ExecutionContractError(f"{purpose} key must be a regular file")
        if before.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ExecutionContractError(
                f"{purpose} key must not be accessible by group or others"
            )
        if exact_size is not None and before.st_size != exact_size:
            raise ExecutionContractError(
                f"{purpose} key must contain exactly {exact_size} bytes"
            )
        if exact_size is None and (before.st_size < 32 or before.st_size > 4096):
            raise ExecutionContractError(
                f"{purpose} key must contain between 32 and 4096 bytes"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 4096))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        key = b"".join(chunks)
        after = os.fstat(descriptor)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if len(key) != before.st_size or any(
            getattr(before, field) != getattr(after, field) for field in stable_fields
        ):
            raise ExecutionContractError(f"{purpose} key changed while reading")
        return key
    finally:
        os.close(descriptor)


def _runtime_config(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> RuntimeConfig:
    registry_path = args.toolchain_registry
    registry_digest = args.toolchain_registry_sha256
    if bool(registry_path) != bool(registry_digest):
        parser.error(
            "--toolchain-registry and --toolchain-registry-sha256 must be supplied together"
        )
    artifact_configuration = (
        args.artifact_root is not None,
        args.artifact_encryption_key_file is not None,
        bool(args.artifact_encryption_key_id),
    )
    if any(artifact_configuration) and not all(artifact_configuration):
        parser.error(
            "--artifact-root, --artifact-encryption-key-file, and "
            "--artifact-encryption-key-id must be supplied together"
        )
    try:
        toolchains = (
            load_toolchain_registry(registry_path, registry_digest)
            if registry_path is not None and registry_digest is not None
            else ()
        )
        signer = (
            ExecutionPermitSigner(
                _read_private_key(
                    args.permit_key_file,
                    purpose="execution permit",
                )
            )
            if args.permit_key_file is not None
            else None
        )
        bundle_signer = (
            HmacEvidenceBundleSigner(
                _read_private_key(
                    args.bundle_signing_key_file,
                    purpose="evidence bundle signing",
                ),
                key_id=args.bundle_signing_key_id,
            )
            if args.bundle_signing_key_file is not None
            else None
        )
        artifact_cipher = (
            AesGcmEnvelopeCipher(
                _read_private_key(
                    args.artifact_encryption_key_file,
                    purpose="artifact encryption",
                    exact_size=32,
                ),
                key_id=args.artifact_encryption_key_id,
            )
            if args.artifact_encryption_key_file is not None
            else None
        )
        return RuntimeConfig(
            artifact_root=args.artifact_root,
            artifact_envelope_cipher=artifact_cipher,
            execution_root=args.execution_root,
            execution_permit_signer=signer,
            toolchains=toolchains,
            bundle_signer=bundle_signer,
        )
    except (ExecutionContractError, OSError, ValueError) as exc:
        parser.error(str(exc))
    raise AssertionError("argparse.error must terminate")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-formal-assurance")
    parser.add_argument("--state", default=":memory:")
    parser.add_argument("--tenant")
    parser.add_argument("--actor", default="local-operator")
    parser.add_argument("--project")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--artifact-encryption-key-file", type=Path)
    parser.add_argument("--artifact-encryption-key-id")
    parser.add_argument("--execution-root", type=Path)
    parser.add_argument("--permit-key-file", type=Path)
    parser.add_argument("--bundle-signing-key-file", type=Path)
    parser.add_argument("--bundle-signing-key-id", default="local-qualification")
    parser.add_argument("--toolchain-registry", type=Path)
    parser.add_argument("--toolchain-registry-sha256")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("skills")
    execute = sub.add_parser("execute")
    execute.add_argument("skill_id")
    execute.add_argument("--request", type=Path, required=True)
    execute.add_argument("--subject", required=True)
    execute.add_argument("--idempotency-key", required=True)
    args = parser.parse_args(argv)
    config = _runtime_config(args, parser)
    store = StateStore(args.state)
    try:
        runtime = FormalAssuranceRuntime(store=store, config=config)
        if args.command == "skills":
            print(
                json.dumps(
                    {"skills": runtime.list_skills()}, ensure_ascii=False, indent=2
                )
            )
            return 0
        if not args.tenant:
            parser.error("--tenant is required for execute")
        request = json.loads(args.request.read_text(encoding="utf-8"))
        identity = TrustedIdentity(args.tenant, args.actor, args.project)
        result = runtime.dispatch(
            args.skill_id,
            request,
            identity,
            subject_id=args.subject,
            idempotency_key=args.idempotency_key,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
