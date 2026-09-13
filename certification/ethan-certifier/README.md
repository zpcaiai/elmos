# Ethan certifier boundary

No private key is permitted in this directory or anywhere else in the
repository. The previous key was exposed through Git and is permanently
revoked by `../KEY_REVOCATION_NOTICE.md`.

The remaining public key is retained only to identify and reject historical
signatures. It is not an active trust anchor. Ethan's replacement private key
must remain outside the repository, and only a newly authenticated public key
fingerprint plus externally signed immutable requests may be imported.

The executable exchange contract is documented in
`EXTERNAL_CERTIFICATION_PROTOCOL.md`. The fixed scope is declared in
`external-certification-plan.json`; M29 is excluded. `external_runner.py` is a
portable, review-before-use capture tool. It deliberately has no private-key or
signing interface.
