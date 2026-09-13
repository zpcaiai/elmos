-- Candidate security surface. Execute after dm8-rls-bootstrap.sql and restart.
-- The executor must use non-SYSDBA test principals for RLS assertions because
-- DM8 RLS policies do not constrain SYSDBA.

CREATE ROLE orders_reader;
CREATE ROLE orders_writer;
GRANT SELECT ON orders TO orders_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON orders TO orders_writer;

CREATE OR REPLACE FUNCTION orders_tenant_predicate(
    schema_name IN VARCHAR,
    object_name IN VARCHAR
) RETURN VARCHAR AS
BEGIN
    RETURN 'tenant_id = SYS_CONTEXT(''ELMOS_APP'', ''TENANT_ID'')';
END;
/

BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema   => USER,
        object_name     => 'ORDERS',
        policy_name     => 'ORDERS_TENANT_POLICY',
        function_schema => USER,
        policy_function => 'ORDERS_TENANT_PREDICATE',
        statement_types => 'SELECT,INSERT,UPDATE,DELETE',
        update_check    => TRUE,
        enable          => TRUE
    );
END;
/
