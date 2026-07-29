\set ON_ERROR_STOP on

-- Run as the migration owner after V61, never as the application runtime role.
-- All values are psql variables. Credentials are deliberately absent: the row
-- stores only an exact Secret Reference resolved by the control-plane process.
--
-- Example:
-- psql "$DATABASE_URL" -f configure_hosted_runtime.sql \
--   -v backend_kind=S3 -v endpoint=https://s3.example.invalid \
--   -v region=cn-north-1 -v bucket=elmos-artifacts \
--   -v path_style=false -v sse=SSE_KMS -v cmk_reference=kms://... \
--   -v credential_reference=secret://object-store/primary \
--   -v data_region=cn-north -v verified_by_actor_id=operator:...

\if :{?backend_kind}
\else
\echo 'backend_kind is required'
\quit 3
\endif
\if :{?endpoint}
\else
\echo 'endpoint is required'
\quit 3
\endif
\if :{?region}
\else
\echo 'region is required'
\quit 3
\endif
\if :{?bucket}
\else
\echo 'bucket is required'
\quit 3
\endif
\if :{?path_style}
\else
\echo 'path_style is required'
\quit 3
\endif
\if :{?sse}
\else
\echo 'sse is required'
\quit 3
\endif
\if :{?cmk_reference}
\else
\set cmk_reference ''
\endif
\if :{?credential_reference}
\else
\echo 'credential_reference is required'
\quit 3
\endif
\if :{?data_region}
\else
\echo 'data_region is required'
\quit 3
\endif
\if :{?verified_by_actor_id}
\else
\echo 'verified_by_actor_id is required'
\quit 3
\endif

BEGIN;

UPDATE object_storage_backends
   SET backend_kind = :'backend_kind',
       endpoint = :'endpoint',
       region = :'region',
       bucket = :'bucket',
       path_style = :'path_style'::boolean,
       server_side_encryption = :'sse',
       cmk_reference = nullif(:'cmk_reference', ''),
       credential_reference = :'credential_reference',
       data_region = :'data_region',
       verified_at = now(),
       verified_by_actor_id = :'verified_by_actor_id',
       backend_state = 'ACTIVE',
       updated_at = now()
 WHERE backend_id = 'primary';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM object_storage_backends
         WHERE backend_id = 'primary' AND backend_state = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION 'ELMOS_PRIMARY_OBJECT_BACKEND_MISSING';
    END IF;
END;
$$;

SELECT backend_id, backend_kind, endpoint, region, bucket, path_style,
       server_side_encryption, cmk_reference, credential_reference,
       backend_state, data_region, verified_at, verified_by_actor_id
  FROM object_storage_backends
 WHERE backend_id = 'primary';

COMMIT;
