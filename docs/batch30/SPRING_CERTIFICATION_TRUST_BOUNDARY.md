# Spring Certification Trust Boundary

## Current decision

The repository may produce local engineering evidence and an unsigned external
review request. It must not create, store, or use private keys for customers,
independent reviewers, runtime verifiers, or certification authorities.

The Spring packs affected by the 2026-09-14 revocation remain
`NOT_CERTIFIED`. External evidence remains `NOT_RUN` until it is supplied by
independent actors through an out-of-repository evidence root and accepted by
the Batch 30 gate.

## Revoked repository evidence

The previous campaign generated its own verifier identities, private keys,
signatures, customer evidence, and certification decision inside the source
repository. Those artifacts did not cross an independent trust boundary. The
current-tree artifacts and admissions have therefore been removed, the exposed
signer has been revoked in every repository trust store, and pack metadata has
been returned to conservative status.

Deleting the files from the current tree does not erase them from Git history.
Repository administrators must treat every historical Spring campaign key as
compromised, rotate any identity that was reused elsewhere, and perform a
coordinated history rewrite only under an explicit repository-wide procedure.

## External intake contract

The external gate requires three independently managed paths, all outside the
repository:

- an evidence root containing the signed role evidence and immutable raw data;
- a non-revoked trust store controlled by the certification authority;
- an unsigned request dossier assembled from the exact repository revision.

`assemble_spring_external_request.py` prepares the unsigned dossier. It never
creates a signature or a private key. `execute_spring_certification_campaign.py`
and the production external gate consume mounted evidence only and reject
repository-contained trust material.

Unknown, missing, stale, synthetic, self-signed, or unreconciled evidence is a
non-success outcome and cannot be promoted to certification.

## Platform boundary

Repository validation, evidence hashing, path normalization, local file locks,
and the autonomous QA control plane support Windows and POSIX hosts. Canonical
evidence paths always use `/` separators and hashes are calculated from exact
binary bytes.

The representative production topology remains rootless Linux and requires the
pinned production toolchain. The autonomous QA trusted delivery service also
retains its POSIX descriptor-relative filesystem boundary; it intentionally
fails closed on Windows rather than replacing race-resistant operations with a
weaker path-based implementation. External OpenSSL execution is `NOT_RUN` on a
host where no independently trusted executable is configured.
