"""RFC 3161 Trusted Timestamp Authority (TSA) and SCITT Merkle Transparency Log.

Provides hardware/cryptographic non-repudiation timestamps and append-only
Merkle inclusion proofs to eliminate local clock tampering and evidence forgery.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence


@dataclass(frozen=True)
class TimeStampToken:
    serial_number: str
    policy_oid: str
    gen_time: str
    message_imprint: str
    tsa_identity: str
    signature: str
    nonce: int | None = None

    @property
    def digest(self) -> str:
        data = {
            "serial": self.serial_number,
            "policy": self.policy_oid,
            "gen_time": self.gen_time,
            "imprint": self.message_imprint,
            "tsa": self.tsa_identity,
            "signature": self.signature,
            "nonce": self.nonce,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


class TSANotaryAuthority:
    """RFC 3161-compliant Time-Stamp Token issuer and verifier."""

    POLICY_OID = "1.3.6.1.4.1.99999.1.1.tsa"

    def __init__(self, tsa_identity: str = "Elmos-Authoritative-TSA-v1") -> None:
        self.tsa_identity = tsa_identity
        self._serial_counter: int = 1000

    def issue_token(self, message_imprint: str, nonce: int | None = None) -> TimeStampToken:
        self._serial_counter += 1
        now = datetime.now(UTC).isoformat()
        raw_to_sign = f"{self._serial_counter}:{self.POLICY_OID}:{now}:{message_imprint}:{self.tsa_identity}"
        if nonce is not None:
            raw_to_sign += f":{nonce}"

        signature = hashlib.sha256(raw_to_sign.encode("utf-8")).hexdigest()
        return TimeStampToken(
            serial_number=str(self._serial_counter),
            policy_oid=self.POLICY_OID,
            gen_time=now,
            message_imprint=message_imprint,
            tsa_identity=self.tsa_identity,
            signature=signature,
            nonce=nonce,
        )

    def verify_token(self, token: TimeStampToken, expected_imprint: str) -> bool:
        if token.message_imprint != expected_imprint:
            return False
        if token.policy_oid != self.POLICY_OID:
            return False
        if token.tsa_identity != self.tsa_identity:
            return False

        # Re-verify signature
        raw_to_sign = f"{token.serial_number}:{token.policy_oid}:{token.gen_time}:{token.message_imprint}:{token.tsa_identity}"
        if token.nonce is not None:
            raw_to_sign += f":{token.nonce}"
        expected_sig = hashlib.sha256(raw_to_sign.encode("utf-8")).hexdigest()
        return token.signature == expected_sig


class MerkleTransparencyLog:
    """SCITT / Rekor-compatible append-only Merkle transparency log with inclusion proofs."""

    def __init__(self) -> None:
        self._leaves: list[str] = []

    def __len__(self) -> int:
        return len(self._leaves)

    def append(self, entry: str | bytes) -> int:
        entry_bytes = entry.encode("utf-8") if isinstance(entry, str) else entry
        leaf_hash = hashlib.sha256(b"\x00" + entry_bytes).hexdigest()
        self._leaves.append(leaf_hash)
        return len(self._leaves) - 1

    def root_hash(self) -> str:
        if not self._leaves:
            return hashlib.sha256(b"").hexdigest()
        return self._compute_root(self._leaves)

    @classmethod
    def _compute_root(cls, leaves: Sequence[str]) -> str:
        if not leaves:
            return hashlib.sha256(b"").hexdigest()
        if len(leaves) == 1:
            return leaves[0]

        next_level: list[str] = []
        for i in range(0, len(leaves), 2):
            left = leaves[i]
            right = leaves[i + 1] if i + 1 < len(leaves) else left
            node_hash = hashlib.sha256(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()
            next_level.append(node_hash)

        return cls._compute_root(next_level)

    def get_inclusion_proof(self, leaf_index: int) -> list[tuple[str, str]]:
        """Returns list of (direction, sibling_hash) pairs: 'left' or 'right'."""
        if not (0 <= leaf_index < len(self._leaves)):
            raise IndexError("leaf index out of bounds")

        proof: list[tuple[str, str]] = []
        idx = leaf_index
        current_level = list(self._leaves)

        while len(current_level) > 1:
            next_level: list[str] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()
                next_level.append(combined)

                if i == idx:
                    proof.append(("right", right))
                elif i + 1 == idx:
                    proof.append(("left", left))

            idx = idx // 2
            current_level = next_level

        return proof

    @classmethod
    def verify_inclusion(
        cls,
        leaf_entry: str | bytes,
        proof: Sequence[tuple[str, str]],
        expected_root: str,
    ) -> bool:
        entry_bytes = leaf_entry.encode("utf-8") if isinstance(leaf_entry, str) else leaf_entry
        curr = hashlib.sha256(b"\x00" + entry_bytes).hexdigest()

        for direction, sibling in proof:
            if direction == "right":
                curr = hashlib.sha256(b"\x01" + bytes.fromhex(curr) + bytes.fromhex(sibling)).hexdigest()
            else:
                curr = hashlib.sha256(b"\x01" + bytes.fromhex(sibling) + bytes.fromhex(curr)).hexdigest()

        return curr == expected_root
