# ADR 0005: Publish complete project trees atomically

**Status:** Accepted

ELMOS builds a versioned complete target tree and switches it atomically. It never publishes by overwriting live output one file at a time. The previous version remains available for rollback under retention policy.
