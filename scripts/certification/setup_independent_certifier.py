#!/usr/bin/env python3
"""Setup independent certifier credentials and trust-store registration.

This tool establishes an independent certifier profile (e.g. Ethan), generates
or imports an RSA keypair, and registers the certifier's trust anchor in a
strictly-formatted trust-store adhering to schemas/test-suite/trust-store.schema.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize independent certifier credentials and trust anchor.")
    parser.add_argument(
        "--certifier-id",
        default="ethan-independent-certifier",
        help="Unique identifier of the independent certifier (default: ethan-independent-certifier)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "certification" / "ethan-certifier",
        help="Directory to store the certifier's keys and metadata",
    )
    parser.add_argument(
        "--trust-store",
        type=Path,
        default=ROOT / "certification" / "trust-store.json",
        help="Path to the external trust-store JSON file",
    )
    parser.add_argument(
        "--valid-days",
        type=int,
        default=365,
        help="Validity period in days (default: 365)",
    )
    parser.add_argument(
        "--bits",
        type=int,
        default=2048,
        choices=[2048, 4096],
        help="RSA key size in bits (default: 2048)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing keys and trust store anchor",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def generate_keypair(out_dir: Path, bits: int, force: bool = False) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    private_key = out_dir / "certifier-private.pem"
    public_key = out_dir / "certifier-public.pem"

    if private_key.exists() and public_key.exists() and not force:
        print(f"Reusing existing keypair at {out_dir}")
        return private_key, public_key

    print(f"Generating {bits}-bit RSA keypair in {out_dir}...")
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-out",
            str(private_key),
            "-pkeyopt",
            f"rsa_keygen_bits:{bits}",
        ],
        check=True,
        capture_output=True,
    )
    os.chmod(private_key, 0o600)

    subprocess.run(
        ["openssl", "rsa", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
        capture_output=True,
    )
    print(f"Generated private key ({private_key.name}) and public key ({public_key.name})")
    return private_key, public_key


def update_trust_store(
    trust_store_path: Path,
    certifier_id: str,
    public_key_path: Path,
    valid_days: int,
) -> dict[str, Any]:
    trust_store_dir = trust_store_path.parent
    trust_store_dir.mkdir(parents=True, exist_ok=True)

    # Store public key relative to trust store directory
    keys_dir = trust_store_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    dest_public_key = keys_dir / f"{certifier_id}.pub.pem"
    dest_public_key.write_bytes(public_key_path.read_bytes())

    pub_sha256 = sha256_file(dest_public_key)
    rel_key_path = str(dest_public_key.relative_to(trust_store_dir))

    now = datetime.now(timezone.utc)
    valid_from = now.isoformat()
    valid_until = (now + timedelta(days=valid_days)).isoformat()

    anchor = {
        "signer_id": certifier_id,
        "roles": ["independent-certifier"],
        "algorithm": "rsa-sha256",
        "revoked": False,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "public_key": rel_key_path,
        "public_key_sha256": pub_sha256,
    }

    trust_store: dict[str, Any] = {"authorities": []}
    if trust_store_path.exists():
        try:
            loaded = json.loads(trust_store_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("authorities"), list):
                trust_store = loaded
        except Exception:
            pass

    # Filter out old anchors with same signer_id
    filtered = [a for a in trust_store["authorities"] if a.get("signer_id") != certifier_id]
    filtered.append(anchor)
    trust_store["authorities"] = filtered

    trust_store_path.write_text(json.dumps(trust_store, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated trust-store at {trust_store_path} with anchor for '{certifier_id}'")
    return anchor


def main() -> int:
    args = parse_args()
    private_key, public_key = generate_keypair(args.output_dir, args.bits, args.force)
    anchor = update_trust_store(args.trust_store, args.certifier_id, public_key, args.valid_days)

    info = {
        "certifier_id": args.certifier_id,
        "private_key": str(private_key.resolve()),
        "public_key": str(public_key.resolve()),
        "public_key_sha256": anchor["public_key_sha256"],
        "trust_store": str(args.trust_store.resolve()),
        "roles": anchor["roles"],
        "valid_until": anchor["valid_until"],
    }
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
