-- Administrative prerequisite for the disposable DM8 Phase-1 target.
-- Run only as an authorized administrator after dm8-rls-bootstrap.sql has
-- enabled and initialized DBMS_RLS. Object grants remain owner-controlled in
-- dm8-security.sql.

CREATE ROLE orders_reader;
CREATE ROLE orders_writer;
CREATE ROLE orders_cdc;
GRANT EXECUTE ON SYS.DBMS_RLS TO ELMOS_APP;
