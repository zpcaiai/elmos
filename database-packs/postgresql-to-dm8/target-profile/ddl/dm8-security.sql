-- Candidate owner security surface. Execute as ELMOS_APP after the authorized
-- administrator has run dm8-security-admin.sql and after the RLS bootstrap
-- restart.
-- The executor must use non-SYSDBA test principals for RLS assertions because
-- DM8 RLS policies do not constrain SYSDBA.

GRANT SELECT ON orders TO orders_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON orders TO orders_writer;
GRANT SELECT ON order_id_seq TO orders_writer;
GRANT EXECUTE ON mark_order_paid TO orders_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON orders TO orders_cdc;
GRANT SELECT ON order_id_seq TO orders_cdc;
GRANT SELECT, INSERT ON order_audit TO orders_cdc;
GRANT SELECT, INSERT ON elmos_cdc_event_ledger TO orders_cdc;
GRANT SELECT, INSERT, UPDATE ON elmos_target_window_journal TO orders_cdc;

CREATE OR REPLACE FUNCTION orders_tenant_predicate(
    schema_name IN VARCHAR,
    object_name IN VARCHAR
) RETURN VARCHAR AS
BEGIN
    -- The development corpus binds synthetic tenant identifiers to the exact
    -- authenticated DM8 principal. This avoids a client-minted application
    -- context and lets negative RLS cases prove cross-tenant isolation.
    RETURN 'USER = ''ELMOS_CDC'' OR tenant_id = USER';
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
