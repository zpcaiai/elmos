# ADR 0002: Stage every generated file before publication

**Status:** Accepted

No generator writes directly into the source repository or live final output. Files are reserved, written to temporary paths, sealed, digest-verified, promoted to CAS, included in a complete tree manifest, validated, and atomically published.
