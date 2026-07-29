-- ELMOS V60: separate one-time runner enrollment from renewable node identity.
--
-- The enrollment credential may bootstrap one exact node for at most one hour.
-- Normal heartbeats and claims use a client-generated node token whose SHA-256
-- alone is stored. Rotation is retry-safe: the client keeps its generated next
-- token and repeats the same request id after an unknown response.

ALTER TABLE runner_enrollment_credentials
    ADD COLUMN claimed_by_runner_node_id varchar(96),
    ADD COLUMN claimed_at timestamptz;

ALTER TABLE runner_node_authentication
    ADD COLUMN node_token_sha256 varchar(64)
        CHECK (node_token_sha256 IS NULL OR node_token_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN previous_node_token_sha256 varchar(64)
        CHECK (previous_node_token_sha256 IS NULL OR previous_node_token_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN node_token_issued_at timestamptz,
    ADD COLUMN node_token_expires_at timestamptz,
    ADD COLUMN previous_token_valid_until timestamptz,
    ADD COLUMN credential_generation integer NOT NULL DEFAULT 0,
    ADD COLUMN last_rotation_request_id varchar(96),
    ADD CONSTRAINT runner_node_authentication_token_shape CHECK (
        node_token_sha256 IS NULL OR (
            node_token_issued_at IS NOT NULL
            AND node_token_expires_at > node_token_issued_at
            AND credential_generation >= 0
        )
    );

CREATE UNIQUE INDEX runner_node_authentication_token_uq
    ON runner_node_authentication (node_token_sha256)
    WHERE node_token_sha256 IS NOT NULL;

COMMENT ON COLUMN runner_enrollment_credentials.claimed_by_runner_node_id IS
    'First successful registration binds this short-lived bootstrap credential to one exact node id; retries for that node remain possible until expiry.';
COMMENT ON COLUMN runner_node_authentication.node_token_sha256 IS
    'SHA-256 of a client-generated renewable node credential. Plaintext exists only in runner memory.';
COMMENT ON COLUMN runner_node_authentication.previous_node_token_sha256 IS
    'Five-minute retry window for an unknown rotation response; accepted only with the exact prior request id and next-token digest.';

REVOKE ALL ON runner_enrollment_credentials FROM PUBLIC;
REVOKE ALL ON runner_node_authentication FROM PUBLIC;
