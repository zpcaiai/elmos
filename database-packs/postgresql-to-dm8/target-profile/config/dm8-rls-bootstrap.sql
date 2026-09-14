-- Run as an authorized DM8 administrator in the disposable target only.
-- ALTER SYSTEM takes effect after the externally orchestrated restart.
-- DM8 MPP is explicitly outside this pilot because DBMS_RLS is unsupported.

ALTER SYSTEM SET 'ENABLE_RLS' = 1 SPFILE;

-- DM8 8.1.4.6 rev244896 exposes the legacy package initializer rather than
-- SP_INIT_RLS_SYS. Keep this idempotent because the image may already contain
-- DBMS_RLS.
DECLARE
  package_count INTEGER;
BEGIN
  SELECT COUNT(*)
    INTO package_count
    FROM V$SYSTEM_PACKAGES
   WHERE NAME = 'DBMS_RLS';

  IF package_count = 0 THEN
    SP_CREATE_SYSTEM_PACKAGES(1, 'DBMS_RLS');
  END IF;
END;
/
