---
name: git-lfs-pointer-object-lock-bandwidth-and-integrity
description: "Implement Git LFS detection, pointer parsing, endpoint authorization, explicit fetch and checkout, object integrity, bandwidth and storage quotas, lock discovery and verification, push checks, provider compatibility, and separate history-rewrite planning."
---

# Objective

Prevent hidden, unbounded LFS downloads and prove which large objects were
available to each task.

# Toolchain

Pin and record:

```text
Git version
Git LFS version
binary digest
installation profile
