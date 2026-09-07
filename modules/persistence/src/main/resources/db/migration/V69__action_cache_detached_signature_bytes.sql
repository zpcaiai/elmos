-- V69 makes lookup-time ActionCache trust a current cryptographic verification, rather than a
-- recheck of signer metadata plus a historical signature digest.
--
-- V67 intentionally retained only the detached signature digest and byte count. Those fields
-- prove that a verifier once saw some bytes, but they cannot verify the signature again after key
-- rotation or revocation. The original signature cannot be reconstructed from its digest, so
-- active signed rows from before V69 are invalidated instead of being upgraded with invented data.

ALTER TABLE cas_action_cache_entries NO FORCE ROW LEVEL SECURITY;

ALTER TABLE cas_action_cache_entries
    ADD COLUMN attestation_signature_value bytea;

UPDATE cas_action_cache_entries
SET invalidated_at = coalesce(invalidated_at, now()),
    invalidation_reason = coalesce(
        invalidation_reason, 'V69_SIGNATURE_BYTES_REQUIRED_FOR_CURRENT_TRUST')
WHERE invalidated_at IS NULL
  AND attestation_key_id IS NOT NULL
  AND attestation_signature_value IS NULL;

ALTER TABLE cas_action_cache_entries
    DROP CONSTRAINT cas_action_attestation_complete_shape,
    ADD CONSTRAINT cas_action_attestation_complete_shape CHECK (
        invalidated_at IS NOT NULL OR (
            (attestation_key_id IS NULL
             AND attestation_algorithm IS NULL
             AND attestation_signature_hex IS NULL
             AND attestation_signature_bytes IS NULL
             AND attestation_signature_value IS NULL
             AND attestation_envelope_version IS NULL
             AND attestation_envelope_hex IS NULL
             AND attestation_envelope_bytes IS NULL
             AND attestation_signed_at_epoch_millis IS NULL
             AND attestation_verified IS NULL)
            OR
            (attestation_key_id IS NOT NULL
             AND attestation_algorithm IS NOT NULL
             AND attestation_signature_hex IS NOT NULL
             AND attestation_signature_bytes IS NOT NULL
             AND attestation_signature_value IS NOT NULL
             AND attestation_envelope_version IS NOT NULL
             AND attestation_envelope_hex IS NOT NULL
             AND attestation_envelope_bytes IS NOT NULL
             AND attestation_signed_at_epoch_millis IS NOT NULL
             AND attestation_verified IS TRUE)
        )
    ),
    ADD CONSTRAINT cas_action_attestation_signature_value_size CHECK (
        attestation_signature_value IS NULL
        OR octet_length(attestation_signature_value) BETWEEN 1 AND 16384
    ),
    ADD CONSTRAINT cas_action_attestation_signature_value_digest_size CHECK (
        attestation_signature_value IS NULL
        OR octet_length(attestation_signature_value) = attestation_signature_bytes
    );

-- The lookup policy deliberately does not reuse write-time signature age as a cache TTL.  The
-- actual insert/update must nevertheless happen inside the same 15-minute presentation window
-- (with one minute of forward clock skew) that the standard verifier enforces.
ALTER TABLE cas_action_cache_entries
    ADD CONSTRAINT cas_action_attestation_write_presentation_window CHECK (
        invalidated_at IS NOT NULL
        OR attestation_key_id IS NULL
        OR (extract(epoch FROM stored_at) * 1000)::numeric BETWEEN
            attestation_signed_at_epoch_millis::numeric - 60000
            AND attestation_signed_at_epoch_millis::numeric + 900000
    );

ALTER TABLE cas_action_cache_entries FORCE ROW LEVEL SECURITY;
