-- Production role hardening check. Run after roles-and-grants.example.sql.
\pset pager off

SELECT n.nspname AS schema_name,
       p.proname AS function_name,
       pg_get_function_identity_arguments(p.oid) AS arguments,
       r.rolname AS owner,
       r.rolcanlogin,
       r.rolbypassrls,
       has_function_privilege('public', p.oid, 'execute') AS public_execute
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_roles r ON r.oid = p.proowner
WHERE p.prosecdef
  AND n.nspname IN ('core','exec','integration','verify','ops')
ORDER BY 1,2,3;

SELECT n.nspname AS schema_name,
       c.relname AS relation_name,
       c.relkind,
       r.rolname AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_roles r ON r.oid = c.relowner
WHERE n.nspname IN ('core','exec','artifact','analysis','generation','transform',
  'verify','metering','cache','integration','learning','ops','audit')
  AND c.relkind IN ('r','p','S','v','m')
  AND r.rolname <> 'elmos_schema_owner'
ORDER BY 1,2;

DO $$
DECLARE
  v_bad_functions integer;
  v_bad_relations integer;
BEGIN
  SELECT count(*) INTO v_bad_functions
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  JOIN pg_roles r ON r.oid = p.proowner
  WHERE p.prosecdef
    AND n.nspname IN ('core','exec','integration','verify','ops')
    AND (
      r.rolname <> 'elmos_runtime_definer'
      OR r.rolcanlogin
      OR NOT r.rolbypassrls
      OR has_function_privilege('public', p.oid, 'execute')
    );
  IF v_bad_functions <> 0 THEN
    RAISE EXCEPTION 'role hardening failed for % SECURITY DEFINER functions', v_bad_functions;
  END IF;

  SELECT count(*) INTO v_bad_relations
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_roles r ON r.oid = c.relowner
  WHERE n.nspname IN ('core','exec','artifact','analysis','generation','transform',
    'verify','metering','cache','integration','learning','ops','audit')
    AND c.relkind IN ('r','p','S','v','m')
    AND r.rolname <> 'elmos_schema_owner';
  IF v_bad_relations <> 0 THEN
    RAISE EXCEPTION 'role hardening failed for % persistent relations', v_bad_relations;
  END IF;
END;
$$;
