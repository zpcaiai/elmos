# ADR 0004: Cache entries carry validation levels

**Status:** Accepted

Cache presence is not evidence. Consumers declare minimum validation levels and reject lower, expired, revoked, trust-mismatched, or scope-mismatched entries.
