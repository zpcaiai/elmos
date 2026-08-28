#!/usr/bin/env python3
"""Applies the whole CAS migration chain (V65.1 -> V66 -> V67 -> V69) to a real PostgreSQL
and asserts the invariants that only a live database can show.

Why this exists separately from verify_v65_migration.py: V66, V67 and V69 each turn
`FORCE ROW LEVEL SECURITY` **off** on a tenant table, do a backfill, and turn it back on.
That is three windows in which a mistake, an early return, or a failed migration could
leave a tenant table forcing nothing for its owner - and no text-level contract test can
see it, because the SQL that restores FORCE is present in the file either way. The only
way to know is to run the chain and read `pg_class.relforcerowsecurity` afterwards.

V66 additionally has a deliberate abort path (`RAISE EXCEPTION` when a provenance digest
cannot be resolved). That path is the interesting one: a migration that fails *after*
dropping FORCE must roll the drop back with it. Phase 2 drives exactly that case.

Needs the `pgserver` wheel; no Docker, no network, no running server.
"""
import pathlib
import sys

try:
    import pgserver
    import psycopg
except ModuleNotFoundError as missing:  # pragma: no cover - environment guard
    raise SystemExit(
        f"missing {missing.name}. This script starts its own PostgreSQL, so it needs:\n"
        "    pip install pgserver 'psycopg[binary]'\n"
        "(no Docker and no running server required)")

CHAIN = [
    "V65_1__content_addressed_store_and_action_cache.sql",
    "V66__cas_resource_bindings_and_complete_metadata.sql",
    "V67__durable_action_cache_index.sql",
    "V69__action_cache_detached_signature_bytes.sql",
]

# Created by V9; the CAS chain hangs its append-only triggers off it.
APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION elmos_forbid_append_only_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'append-only table % cannot be updated or deleted', TG_TABLE_NAME;
END;
$$;
"""

TENANT_TABLES = [
    "cas_object_catalog",
    "cas_object_placement",
    "cas_action_cache_entries",
    "cas_reference_roots",
    "cas_upload_sessions",
    "cas_deletion_manifests",
    "cas_quarantine_events",
    "cas_resource_bindings",
    "cas_action_cache_invalidations",
    "cas_action_cache_quarantined_nodes",
]

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "e" * 64
IMAGE = "registry.internal/elmos/java21@sha256:" + "d" * 64

failures = []
checks = 0


def migration_dir() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "modules" / "persistence" / "src" / "main" / "resources" / "db" / "migration"
        if candidate.is_dir():
            return candidate
    raise SystemExit("cannot find modules/persistence/src/main/resources/db/migration; "
                     "run this from inside the elmos repository")


def check(condition, label, detail=""):
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{': ' + detail if detail else ''}")


def run(uri, sql, *, expect_error=None, label=""):
    """One statement, one connection, so a rejection cannot poison later work."""
    global checks
    checks += 1
    try:
        with psycopg.connect(uri, autocommit=True) as connection:
            connection.execute(sql)
        if expect_error:
            failures.append(f"{label}: expected rejection ({expect_error}) but it succeeded")
    except psycopg.Error as error:
        text = str(error)
        if not expect_error:
            failures.append(f"{label}: unexpected failure -> {text[:280]}")
        elif expect_error not in text:
            failures.append(f"{label}: expected {expect_error!r}, got {text[:280]}")


def query(uri, sql, params=None):
    with psycopg.connect(uri, autocommit=True) as connection:
        return connection.execute(sql, params).fetchall()


def force_rls_state(uri):
    """relrowsecurity / relforcerowsecurity straight out of the catalog."""
    rows = query(uri, """
        SELECT relname, relrowsecurity, relforcerowsecurity
          FROM pg_class
         WHERE relname LIKE 'cas\\_%' AND relkind = 'r'
         ORDER BY relname
    """)
    return {name: (enabled, forced) for name, enabled, forced in rows}


def apply_chain(uri, directory, upto=None):
    run(uri, APPEND_ONLY_FUNCTION, label="append-only function")
    for name in CHAIN:
        if upto and name > upto:
            break
        run(uri, (directory / name).read_text(), label=f"{name[:3]} applies")


def active_entry_sql(key, *, signed_offset_ms=0, signature_bytes=64, extra=""):
    """A fully valid active row post-V69, parameterised where a negative test needs it.

    Every column the V67 `cas_action_active_metadata_complete` constraint demands has to be
    present, which is the point: an active row must carry enough to rebuild the typed entry.
    """
    return f"""
    INSERT INTO cas_action_cache_entries (
        organization_id, action_key_hex, project_id, action_id, receipt_id, attempt,
        lease_generation, result_status, exit_code, validation_status,
        output_manifest_hex, output_manifest_bytes, provenance_digest_hex, provenance_digest_bytes,
        toolchain_image, producer_permission_scope, producer_residency, producer_security_tier,
        producer_sensitivity, risk_tier, writer_service_id, writer_trust_domain, writer_node_id,
        wall_seconds, cpu_seconds, stored_at,
        action_key_bytes, action_component_names, action_component_values,
        result_schema_version, result_started_at, result_finished_at,
        writer_attested, max_memory_mb, read_bytes, written_bytes, gpu_seconds,
        cost_names, cost_values,
        attestation_key_id, attestation_algorithm, attestation_signature_hex,
        attestation_signature_bytes, attestation_signature_value,
        attestation_envelope_version, attestation_envelope_hex, attestation_envelope_bytes,
        attestation_signed_at_epoch_millis, attestation_verified
        {extra}
    ) VALUES (
        'org-a', '{key}', 'proj-a', 'act-1', 'receipt-1', 1,
        1, 'SUCCEEDED', 0, 'PASS',
        '{HEX_A}', 240, '{HEX_A}', 240,
        '{IMAGE}', ARRAY['repo:read'], 'eu-west', 'INTERNAL',
        'GENERATED_OUTPUT', 'HIGH', 'cas-writer', 'elmos.internal', 'ns/runners/sa/n1',
        1.0, 1.0, now(),
        128, ARRAY['source_tree'], ARRAY['sha256:x'],
        '1.0', '2026-08-25T00:00:00Z', '2026-08-25T00:01:00Z',
        true, 64.0, 10, 10, 0.0,
        ARRAY['compute_usd'], ARRAY[0.12],
        'kms-1', 'Ed25519', '{HEX_B}',
        {signature_bytes}, decode(repeat('61', 64), 'hex'),
        'elmos-result-signature/2', '{HEX_C}', 512,
        (extract(epoch FROM now()) * 1000)::bigint + {signed_offset_ms}, true
    );
    """


def phase_one(server, directory):
    print("--- phase 1: the whole chain applies and FORCE RLS survives it")
    server.psql("CREATE DATABASE chain")
    uri = server.get_uri(database="chain")
    apply_chain(uri, directory)

    state = force_rls_state(uri)
    for table in TENANT_TABLES:
        enabled, forced = state.get(table, (None, None))
        check(enabled is True, f"{table}: ROW LEVEL SECURITY not enabled", str(enabled))
        # The headline assertion. Three migrations drop FORCE mid-flight; if any of them
        # failed to put it back, the table owner silently bypasses tenant isolation.
        check(forced is True, f"{table}: FORCE ROW LEVEL SECURITY was not restored", str(forced))

    policies = {name for (name,) in query(uri, """
        SELECT DISTINCT policyname FROM pg_policies WHERE tablename LIKE 'cas\\_%'
    """)}
    check({"cas_b65_tenant_isolation", "cas_b66_tenant_isolation",
           "cas_b67_tenant_isolation"} <= policies,
          "not every CAS tenant-isolation policy exists", str(sorted(policies)))

    check(not query(uri, """
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'cas_object_catalog' AND column_name = 'project_id'
    """), "V66 did not drop cas_object_catalog.project_id")
    return uri


def phase_two(server, directory):
    print("--- phase 2: V66's abort path must roll FORCE back with it")
    server.psql("CREATE DATABASE abortpath")
    uri = server.get_uri(database="abortpath")
    apply_chain(uri, directory, upto=CHAIN[0])

    # A catalogued object whose provenance digest is not itself catalogued. V66 refuses to
    # invent a size for it, which is the behaviour under test.
    run(uri, f"""
        INSERT INTO cas_object_catalog (organization_id, digest_hex, size_bytes, project_id,
            object_kind, media_type, source_system, schema_version, sensitivity,
            retention_class, data_residency, security_tier, provenance_digest_hex)
        VALUES ('org-a', '{HEX_A}', 10, 'proj-a', 'BLOB', 'application/octet-stream', 'elmos',
            '1.0', 'GENERATED_OUTPUT', 'STANDARD', 'eu-west', 'INTERNAL', '{HEX_B}');
    """, label="seed a row whose provenance object is absent")

    before = force_rls_state(uri)["cas_object_catalog"][1]
    check(before is True, "precondition: FORCE was not set before V66", str(before))

    run(uri, (directory / CHAIN[1]).read_text(),
        expect_error="cannot infer provenance size",
        label="V66 aborts rather than inventing a provenance size")

    after = force_rls_state(uri)["cas_object_catalog"][1]
    # This is the crown jewel. A migration that fails after `NO FORCE ROW LEVEL SECURITY`
    # must take the drop down with it, or a failed deploy silently disables tenant isolation
    # for the owner role and nothing downstream notices.
    check(after is True,
          "FORCE ROW LEVEL SECURITY stayed OFF after V66 aborted - tenant isolation is weakened",
          str(after))


def phase_three(uri):
    print("--- phase 3: the constraints V66/V67/V69 added actually fire")

    # V66: provenance digest and size are both-or-neither.
    run(uri, f"""
        INSERT INTO cas_object_catalog (organization_id, digest_hex, size_bytes,
            object_kind, media_type, source_system, schema_version, sensitivity,
            retention_class, data_residency, security_tier, provenance_digest_hex)
        VALUES ('org-a', '{HEX_A}', 10, 'BLOB', 'text/plain', 'elmos', '1.0',
            'GENERATED_OUTPUT', 'STANDARD', 'eu-west', 'INTERNAL', '{HEX_B}');
    """, expect_error="cas_object_catalog_provenance_digest_complete",
        label="V66: a provenance digest without its size is refused")

    run(uri, f"""
        INSERT INTO cas_object_catalog (organization_id, digest_hex, size_bytes,
            object_kind, media_type, source_system, schema_version, sensitivity,
            retention_class, data_residency, security_tier)
        VALUES ('org-a', '{HEX_A}', 10, 'BLOB', 'text/plain', 'elmos', '1.0',
            'GENERATED_OUTPUT', 'STANDARD', 'eu-west', 'INTERNAL');
    """, label="V66: a row with no provenance at all is accepted")

    # V66: resource bindings.
    run(uri, f"""
        INSERT INTO cas_resource_bindings (organization_id, resource_kind, resource_id, digest_hex)
        VALUES ('org-a', 'REPOSITORY', 'github.com/acme/app', '{HEX_A}');
    """, label="V66: a repository binding is accepted")
    run(uri, f"""
        INSERT INTO cas_resource_bindings (organization_id, resource_kind, resource_id, digest_hex)
        VALUES ('org-a', 'WORKSPACE', 'w-1', '{HEX_A}');
    """, expect_error="cas_resource_bindings_resource_kind_check",
        label="V66: an unknown resource kind is refused")
    run(uri, f"""
        INSERT INTO cas_resource_bindings (organization_id, resource_kind, resource_id, digest_hex)
        VALUES ('org-a', 'PROJECT', '   ', '{HEX_A}');
    """, expect_error="cas_resource_bindings_resource_id_check",
        label="V66: a blank resource id is refused")
    run(uri, f"""
        INSERT INTO cas_resource_bindings (organization_id, resource_kind, resource_id, digest_hex)
        VALUES ('org-a', 'PROJECT', 'p-1', '{HEX_C}');
    """, expect_error="cas_resource_bindings_organization_id_digest_hex_fkey",
        label="V66: binding an uncatalogued object is refused")
    run(uri, f"""
        INSERT INTO cas_resource_bindings (organization_id, resource_kind, resource_id,
            digest_hex, bound_at, released_at)
        VALUES ('org-a', 'PROJECT', 'p-2', '{HEX_A}', now(), now() - interval '1 hour');
    """, expect_error="cas_resource_bindings_release_after_bind",
        label="V66: releasing a binding before it was bound is refused")

    # V69 / V67: the action cache entry shape.
    run(uri, active_entry_sql(HEX_A), label="V69: a fully signed active entry is accepted")
    run(uri, active_entry_sql(HEX_B, signature_bytes=1),
        expect_error="cas_action_attestation_signature_value_digest_size",
        label="V69: a signature byte count that contradicts the bytes is refused")
    run(uri, active_entry_sql(HEX_B, signed_offset_ms=-1_800_000),
        expect_error="cas_action_attestation_write_presentation_window",
        label="V69: a signature older than the presentation window is refused at write time")
    # The window is deliberately asymmetric: a signature may be up to 15 minutes old, but only
    # one minute ahead. Age is normal (sign, then write); a signature dated into the future is
    # either a broken clock or a forged timestamp, so the tolerance there is nearly nothing.
    run(uri, active_entry_sql(HEX_B, signed_offset_ms=-600_000),
        label="V69: a ten-minute-old signature is still inside the presentation window")
    run(uri, active_entry_sql(HEX_C, signed_offset_ms=600_000),
        expect_error="cas_action_attestation_write_presentation_window",
        label="V69: a signature dated ten minutes into the future is refused")

    run(uri, f"""
        INSERT INTO cas_action_cache_entries (organization_id, action_key_hex, project_id,
            action_id, receipt_id, attempt, lease_generation, result_status, exit_code,
            validation_status, output_manifest_hex, output_manifest_bytes,
            provenance_digest_hex, toolchain_image, producer_permission_scope,
            producer_residency, producer_security_tier, producer_sensitivity, risk_tier,
            writer_service_id, writer_trust_domain, writer_node_id)
        VALUES ('org-a', '{HEX_D}', 'proj-a', 'act-1', 'receipt-1', 1, 1, 'SUCCEEDED', 0,
            'PASS', '{HEX_A}', 240, '{HEX_A}', '{IMAGE}', ARRAY['repo:read'], 'eu-west',
            'INTERNAL', 'GENERATED_OUTPUT', 'STANDARD', 'cas-writer', 'elmos.internal', 'n1');
    """, expect_error="cas_action_active_metadata_complete",
        label="V67: an active entry missing the rebuild metadata is refused")


def phase_four(uri):
    print("--- phase 3b: RLS actually isolates the table V66 added")
    run(uri, "CREATE ROLE elmos_app_v66 LOGIN", label="application role created")
    run(uri, "GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO elmos_app_v66",
        label="application role granted")

    def as_tenant(organization, sql, fetch=False):
        with psycopg.connect(uri, autocommit=True) as connection:
            connection.execute("SET ROLE elmos_app_v66")
            connection.execute("SELECT set_config('app.organization_id', %s, false)", (organization,))
            cursor = connection.execute(sql)
            return cursor.fetchall() if fetch else None

    visible_to_other = as_tenant("org-b", "SELECT count(*) FROM cas_resource_bindings", fetch=True)
    check(visible_to_other[0][0] == 0, "RLS did not hide org-a bindings from org-b",
          str(visible_to_other))
    own = as_tenant("org-a", "SELECT count(*) FROM cas_resource_bindings", fetch=True)
    check(own[0][0] > 0, "RLS hid org-a bindings from org-a", str(own))

    global checks
    checks += 1
    try:
        as_tenant("org-b", f"""
            INSERT INTO cas_resource_bindings (organization_id, resource_kind, resource_id,
                digest_hex) VALUES ('org-a', 'PROJECT', 'stolen', '{HEX_A}')
        """)
        failures.append("a tenant could write a binding into another tenant")
    except psycopg.Error as error:
        if "row-level security" not in str(error):
            failures.append(f"cross-tenant write failed for the wrong reason: {error}")


def main():
    directory = migration_dir()
    missing = [name for name in CHAIN if not (directory / name).is_file()]
    if missing:
        raise SystemExit(f"missing migrations: {missing}")

    import tempfile
    server = pgserver.get_server(tempfile.mkdtemp(prefix="elmos-cas-chain-"))
    print("postgres:", query(server.get_uri(), "select version()")[0][0].split(" on ")[0])
    print("chain:", " -> ".join(name[:3] for name in CHAIN))
    print()

    uri = phase_one(server, directory)
    phase_two(server, directory)
    phase_three(uri)
    phase_four(uri)

    print()
    print(f"checks executed: {checks}")
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for failure in failures:
            print("  -", failure)
        return 1
    print("the V65->V69 chain applies, FORCE RLS survives all three drop/restore windows "
          "(including V66's abort path), and every new constraint behaved as specified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
