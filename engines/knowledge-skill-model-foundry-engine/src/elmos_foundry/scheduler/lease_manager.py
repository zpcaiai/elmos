from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class Lease:
    resource_id: str
    owner_id: str
    fencing_token: int
    expires_at: float
    renew_count: int = 0
    metadata: Dict[str, str] = field(default_factory=dict)


class DistributedLeaseManager:
    """Manages lease fencing and heartbeat renewals for distributed workers."""

    def __init__(self, default_ttl: float = 15.0):
        self.default_ttl = default_ttl
        self._lock = threading.Lock()
        self._leases: Dict[str, Lease] = {}
        self._fencing_counter = 1000

    def acquire(self, resource_id: str, owner_id: str, ttl: Optional[float] = None) -> Tuple[bool, int]:
        """Attempt to acquire lease. Returns (acquired, fencing_token)."""
        duration = ttl if ttl is not None else self.default_ttl
        now = time.time()
        with self._lock:
            existing = self._leases.get(resource_id)
            if existing is not None:
                if now < existing.expires_at and existing.owner_id != owner_id:
                    # Still held by another alive owner
                    return False, 0

            # Acquire new lease or replace expired lease
            self._fencing_counter += 1
            token = self._fencing_counter
            lease = Lease(
                resource_id=resource_id,
                owner_id=owner_id,
                fencing_token=token,
                expires_at=now + duration,
            )
            self._leases[resource_id] = lease
            return True, token

    def heartbeat(self, resource_id: str, owner_id: str, fencing_token: int, ttl: Optional[float] = None) -> bool:
        """Renew an active lease if owner and fencing token match."""
        duration = ttl if ttl is not None else self.default_ttl
        now = time.time()
        with self._lock:
            lease = self._leases.get(resource_id)
            if lease is None:
                return False
            if lease.owner_id != owner_id or lease.fencing_token != fencing_token:
                return False
            if now > lease.expires_at:
                return False  # Expired before heartbeat arrived

            lease.expires_at = now + duration
            lease.renew_count += 1
            return True

    def validate_fencing_token(self, resource_id: str, fencing_token: int) -> bool:
        """Verify that a worker's fencing token is still current and not superseded."""
        now = time.time()
        with self._lock:
            lease = self._leases.get(resource_id)
            if lease is None:
                return False
            if lease.fencing_token != fencing_token:
                return False
            return now <= lease.expires_at

    def release(self, resource_id: str, owner_id: str, fencing_token: int) -> bool:
        with self._lock:
            lease = self._leases.get(resource_id)
            if lease is None:
                return False
            if lease.owner_id == owner_id and lease.fencing_token == fencing_token:
                del self._leases[resource_id]
                return True
            return False

    def reap_stale(self) -> int:
        """Reap all expired leases. Returns number of reclaimed resources."""
        now = time.time()
        reaped = 0
        with self._lock:
            stale_keys = [k for k, v in self._leases.items() if now > v.expires_at]
            for k in stale_keys:
                del self._leases[k]
                reaped += 1
        return reaped
