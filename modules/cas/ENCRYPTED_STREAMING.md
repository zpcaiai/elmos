# Encrypted CAS streaming contract

New `put(byte[])` and `putDurable(InputStream)` writes use `ELMOS-CAS-ENC/3`.
`openVerified` authenticates every frame and verifies the complete plaintext size/SHA-256
into an owned private spool **before returning any plaintext stream**. Returned streams own
and remove that spool; later ciphertext pathname changes cannot change verified output.
Byte-array `get` still allocates its result as required by that compatibility API.

## Format and provider boundary

- A fresh random 256-bit object key encrypts independent 64 KiB AES-GCM frames. No custom
  cipher or GHASH is implemented; encryption uses the installed JCE AES-GCM provider.
- The existing tenant encryption provider encrypts one small key descriptor containing the
  object key, exact plaintext digest and size. Its real descriptor digest is used as the
  provider's authenticated identity. Directory key versioning and KMS context/state checks
  remain authoritative. Wrapping is per object, not per frame.
- Header fields: v3 magic, descriptor SHA-256, bounded key-id length/key-id, bounded wrapped
  descriptor length/bytes, and an eight-byte nonce prefix. A frame nonce is prefix plus its
  four-byte index. Each independent object key is fresh; the maximum object policy is 1 TiB,
  below the frame-index exhaustion boundary.
- Frame AAD binds format, tenant, exact object digest/size, descriptor digest/size, frame
  index and plaintext frame length. The digest determines exact frame lengths/count. Empty
  objects have one authenticated empty frame. Extra, reordered or truncated frames fail.
- The wrapped descriptor is re-opened after long encryption/decryption before publication
  or plaintext exposure, so revoked/unavailable key state is not treated as successful data.
  Provider failures do not quarantine valid ciphertext; integrity failures do.

The default object limit is 1 GiB. The host constructor can set a lower limit or increase it
up to 1 TiB. Per-operation crypto allocations are bounded by frames and the provider envelope
budget (at most 1 MiB overhead). These are not an aggregate disk-admission quota; hosts must
budget concurrent private plaintext spools and encrypted staging space.

## Legacy v2 and rollout

V2 ciphertext remains readable, including key rotation. Its monolithic JCE decrypt operation
is **not** memory-bounded by a frame: the default legacy plaintext limit is 64 MiB. An exact
host-owned constructor parameter can increase this explicit compatibility budget, up to
the representable byte-array limit. Over-budget reads fail with
`CAS_LEGACY_V2_REQUIRES_BOUNDED_OFFLINE_MIGRATION`; they do not quarantine the valid object.

For old large objects, use a separately budgeted, authorized offline migration process:
instantiate the source with an explicit sufficient legacy limit, call `openVerified`, and
feed its returned stream to a **different** destination v3 CAS root via `putDurable`. Verify
every digest and tenant/key binding there before a separately authorized storage cutover.
The automated read-old/write-new test covers this path. Do not overwrite ciphertext in place,
silently bypass legacy bounds, or treat source retirement as authorized by this code change.

An old binary does not understand v3. Coordinate reader rollout before v3 writes and retain
the old root until rollback/retention policy permits retirement. Rolling back to a v2-only
binary against a v3-containing root is unsupported; this change does not perform deployment.

## Local verification

`EncryptedCasStreamingTest` covers frame boundaries, empty content, late authentication failure,
truncation, suffix data, reorder, tenant isolation, key rotation, concurrent immutable winners,
owned verified reads, invalid producers, and bounded legacy read/new-format write.
`EncryptedStreamingHeapProbe` exercises a real 128 MiB object under `-Xmx64m`; this bounds JVM
heap for the local v3 path, not RSS, disk, provider concurrency or production performance.
These are local engineering checks, not independent cryptographic audit or certification.
