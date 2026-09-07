-- Migration Pack Certification M29-M34 admission and gate receipts.
-- The control plane can prepare evidence but only the named pack script can issue a gate receipt.

CREATE SCHEMA IF NOT EXISTS migration_pack_certification;

DO $$
DECLARE
    table_name text;
    batch_tables text[] := ARRAY[
        'pack_admissions',
        'phase_evidence',
        'support_matrix_snapshots',
        'pack_gate_receipts',
        'certification_records',
        'pack_audit_events'
    ];
BEGIN
    FOREACH table_name IN ARRAY batch_tables LOOP
        EXECUTE format(
            'CREATE TABLE migration_pack_certification.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'pack_id varchar(3) NOT NULL CHECK (pack_id IN (''M29'',''M30'',''M31'',''M32'',''M33'',''M34'')),' ||
            'assessment_id varchar(160) NOT NULL,' ||
            'source_snapshot_digest varchar(64) NOT NULL CHECK (source_snapshot_digest ~ ''^[0-9a-f]{64}$''),' ||
            'target_snapshot_digest varchar(64) NOT NULL CHECK (target_snapshot_digest ~ ''^[0-9a-f]{64}$''),' ||
            'pack_version varchar(96) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''NOT_RUN'' CHECK (status IN (''NOT_RUN'',''INCONCLUSIVE'',''BLOCKED'',''READY_FOR_PACK_GATE'',''GATE_PASSED'',''GATE_FAILED'')),' ||
            'gate_authority varchar(256) NOT NULL,' ||
            'gate_receipt_ref varchar(512),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
            'certified boolean NOT NULL DEFAULT false,' ||
            'production_mutation_executed boolean NOT NULL DEFAULT false CHECK (production_mutation_executed = false),' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (NOT certified OR (status = ''GATE_PASSED'' AND gate_receipt_ref IS NOT NULL AND jsonb_array_length(evidence_refs) > 0)),' ||
            'CHECK (status NOT IN (''READY_FOR_PACK_GATE'',''GATE_PASSED'') OR jsonb_array_length(evidence_refs) > 0),' ||
            'UNIQUE (organization_id, pack_id, idempotency_key))', table_name);
        EXECUTE format('ALTER TABLE migration_pack_certification.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE migration_pack_certification.%I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON migration_pack_certification.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))', table_name);
        EXECUTE format(
            'CREATE TRIGGER migration_pack_append_only BEFORE UPDATE OR DELETE ON migration_pack_certification.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()', table_name);
    END LOOP;
END;
$$;
