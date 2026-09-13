-- Run as an authorized DM8 administrator in the disposable target only.
-- ALTER SYSTEM takes effect after the externally orchestrated restart.
-- DM8 MPP is explicitly outside this pilot because DBMS_RLS is unsupported.

ALTER SYSTEM SET 'ENABLE_RLS' = 1 SPFILE;
SP_INIT_RLS_SYS(1);
