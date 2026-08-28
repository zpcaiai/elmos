#!/usr/bin/env python3
"""Runs V65 against a real PostgreSQL and asserts the constraints actually fire.

Applying DDL proves it parses. What this script proves is stronger: every CHECK,
unique index, append-only trigger and RLS policy in the migration is exercised with a
row that must be refused, and the refusal is asserted by SQLSTATE.

Requires the `pgserver` wheel (bundles a PostgreSQL binary); no Docker, no network.
"""
import pathlib
import sys
import tempfile

try:
    import pgserver
    import psycopg
except ModuleNotFoundError as missing:  # pragma: no cover - environment guard
    raise SystemExit(
        f"missing {missing.name}. This script starts its own PostgreSQL, so it needs:\n"
        f"    {sys.executable} -m pip install pgserver 'psycopg[binary]'\n"
        "(no Docker and no running server required)\n"
        "\n"
        "Use THAT interpreter, not a bare `pip`: on a Homebrew Mac `pip` and\n"
        "`python3` are frequently different Pythons, and installing into one\n"
        "while running the other reports success and still fails here.\n"
        "`scripts/cas/finish-mac-verification.sh` picks a consistent one for you.")

MIGRATION_NAME = "V65_1__content_addressed_store_and_action_cache.sql"


def locate_migration() -> pathlib.Path:
    """Finds the migration wherever this script is run from.

    It lives in modules/persistence with the other Flyway migrations, not next to this
    script - copying it here would create a second copy that drifts from the one that
    actually gets applied.
    """
    here = pathlib.Path(__file__).resolve()
    candidates = [here.with_name(MIGRATION_NAME)]
    for parent in here.parents:
        candidates.append(parent / "modules" / "persistence" / "src" / "main" / "resources"
                          / "db" / "migration" / MIGRATION_NAME)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        f"cannot find {MIGRATION_NAME}. Run this from inside the elmos repository, or place "
        f"the migration next to this script. Looked in:\n  "
        + "\n  ".join(str(candidate) for candidate in candidates[:4]))


MIGRATION = locate_migration()

# V9 creates this; V65 depends on it. Reproduced verbatim so the migration can be
# exercised standalone.
APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION elmos_forbid_append_only_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'append-only table % cannot be updated or deleted', TG_TABLE_NAME;
END;
$$;
"""

HEX = "a" * 64
HEX2 = "b" * 64
IMAGE = "registry.internal/elmos/java21@sha256:" + "c" * 64

CATALOG_ROW = """
INSERT INTO cas_object_catalog (organization_id, digest_hex, size_bytes, project_id, object_kind,
    media_type, source_system, schema_version, sensitivity, retention_class, data_residency,
    security_tier, provenance_digest_hex)
VALUES ('org-a', '{hex}', 1024, 'proj-a', 'BLOB', 'application/octet-stream', 'elmos', '1.0',
    '{sensitivity}', 'STANDARD', 'eu-west', 'INTERNAL', {provenance});
"""

ACTION_ROW = """
INSERT INTO cas_action_cache_entries (organization_id, action_key_hex, project_id, action_id,
    receipt_id, attempt, lease_generation, result_status, exit_code, failure_class,
    validation_status, output_manifest_hex, output_manifest_bytes, provenance_digest_hex,
    toolchain_image, producer_permission_scope, producer_residency, producer_security_tier,
    producer_sensitivity, risk_tier, writer_service_id, writer_trust_domain, writer_node_id,
    attestation_key_id, attestation_signature_hex, expires_at)
VALUES ('org-a', '{key}', 'proj-a', 'act-1', 'receipt-1', 1, 1, '{status}', {exit_code},
    {failure_class}, 'PASS', '{hex}', 240, '{hex}', '{image}', ARRAY['repo:read'], 'eu-west',
    'INTERNAL', 'GENERATED_OUTPUT', '{risk}', 'cas-writer', 'elmos.internal', 'ns/runners/sa/n1',
    {key_id}, {signature}, {expires});
"""

failures = []
checks = 0


def run(uri, sql, *, expect_error=None, label=""):
    """Runs one statement on its own connection so a rejection cannot poison later work."""
    global checks
    checks += 1
    try:
        with psycopg.connect(uri, autocommit=True) as connection:
            connection.execute(sql)
        if expect_error:
            failures.append(f"{label}: expected rejection ({expect_error}) but the statement succeeded")
    except psycopg.Error as error:
        text = str(error)
        if not expect_error:
            failures.append(f"{label}: unexpected failure -> {text[:300]}")
        elif expect_error not in text:
            failures.append(f"{label}: expected {expect_error!r} in error, got {text[:300]}")


def query(uri, sql):
    with psycopg.connect(uri, autocommit=True) as connection:
        return connection.execute(sql).fetchall()


def main():
    global checks
    data_dir = tempfile.mkdtemp(prefix="elmos-v65-")
    server = pgserver.get_server(data_dir)
    uri = server.get_uri()
    print("postgres:", query(uri, "select version();")[0][0].split(" on ")[0])

    run(uri, APPEND_ONLY_FUNCTION, label="append-only function")
    run(uri, MIGRATION.read_text(), label="V65 applies")

    tables = [row[0] for row in query(uri,
        "select tablename from pg_tables where schemaname='public' and tablename like 'cas\\_%' order by 1")]
    for expected in ["cas_action_cache_entries", "cas_deletion_manifests", "cas_object_catalog",
                     "cas_object_placement", "cas_quarantine_events", "cas_reference_roots",
                     "cas_upload_sessions"]:
        checks += 1
        if expected not in tables:
            failures.append(f"table {expected} was not created")

    policies = [row[0] for row in query(uri,
        "select tablename from pg_policies where policyname='cas_b65_tenant_isolation' order by 1")]
    checks += 1
    if len(policies) != 7:
        failures.append(f"expected 7 RLS policies, got: {policies}")

    forced = [row[0] for row in query(uri,
        "select relname from pg_class where relname like 'cas\\_%' and relrowsecurity"
        " and relforcerowsecurity order by 1")]
    checks += 1
    if len(forced) != 7:
        failures.append(f"expected 7 tables with FORCE ROW LEVEL SECURITY, got: {forced}")

    # --- catalogue constraints -------------------------------------------------
    run(uri, CATALOG_ROW.format(hex=HEX, sensitivity="GENERATED_OUTPUT", provenance="NULL"),
        label="catalogue accepts a private object without provenance")
    run(uri, CATALOG_ROW.format(hex=HEX2, sensitivity="PUBLIC_DEPENDENCY", provenance="NULL"),
        expect_error="cas_object_catalog_shared_needs_provenance",
        label="shared content without provenance is refused")
    run(uri, CATALOG_ROW.format(hex=HEX2, sensitivity="PUBLIC_DEPENDENCY", provenance=f"'{HEX}'"),
        label="shared content with provenance is accepted")
    run(uri, CATALOG_ROW.format(hex=HEX.upper(), sensitivity="GENERATED_OUTPUT", provenance="NULL"),
        expect_error="cas_object_catalog_digest_hex_check",
        label="uppercase digest hex is refused")
    run(uri, "INSERT INTO cas_object_catalog (organization_id, digest_hex, size_bytes, project_id,"
                " object_kind, media_type, source_system, schema_version, sensitivity, retention_class,"
                " data_residency, security_tier) VALUES ('org-a', '" + "d" * 64 + "', -1, 'p', 'BLOB',"
                " 'text/plain', 'elmos', '1.0', 'PRIVATE_SOURCE', 'STANDARD', 'eu-west', 'INTERNAL');",
        expect_error="cas_object_catalog_size_bytes_check", label="negative size is refused")

    # --- placement -------------------------------------------------------------
    run(uri, f"INSERT INTO cas_object_placement (organization_id, digest_hex, region, placement_role,"
                f" storage_tier) VALUES ('org-a', '{HEX}', 'eu-west-1', 'PRIMARY', 'L2');",
        label="primary placement accepted")
    run(uri, f"INSERT INTO cas_object_placement (organization_id, digest_hex, region, placement_role,"
                f" storage_tier) VALUES ('org-a', '{HEX}', 'eu-central-1', 'REPLICA', 'L2');",
        label="replica placement accepted")
    run(uri, f"INSERT INTO cas_object_placement (organization_id, digest_hex, region, placement_role,"
                f" storage_tier) VALUES ('org-a', '{HEX}', 'us-east-1', 'PRIMARY', 'L2');",
        expect_error="cas_object_placement_single_primary_uq",
        label="a second primary region is refused")
    run(uri, f"INSERT INTO cas_object_placement (organization_id, digest_hex, region, placement_role,"
                f" storage_tier) VALUES ('org-a', '{'e' * 64}', 'eu-west-1', 'PRIMARY', 'L2');",
        expect_error="cas_object_placement_organization_id_digest_hex_fkey",
        label="placement of an uncatalogued object is refused")

    # --- action cache ----------------------------------------------------------
    def action(**overrides):
        values = dict(key=HEX, status="SUCCEEDED", exit_code=0, failure_class="NULL", hex=HEX,
                      image=IMAGE, risk="STANDARD", key_id="NULL", signature="NULL", expires="NULL")
        values.update(overrides)
        return ACTION_ROW.format(**values)

    run(uri, action(), label="a standard successful entry is accepted")
    run(uri, action(key=HEX2, status="SUCCEEDED", exit_code=3),
        expect_error="cas_action_cache_success_has_zero_exit",
        label="SUCCEEDED with a non-zero exit code is refused")
    run(uri, action(key=HEX2, status="FAILED", exit_code=1, failure_class="NULL"),
        expect_error="cas_action_cache_failure_is_classified",
        label="FAILED without a failure class is refused")
    run(uri, action(key=HEX2, status="FAILED", exit_code=1, failure_class="'ENVIRONMENT'",
                       expires="now() + interval '1 hour'"),
        expect_error="cas_action_cache_failure_ttl",
        label="a transient failure cannot be cached")
    run(uri, action(key=HEX2, status="FAILED", exit_code=1, failure_class="'CODE'", expires="NULL"),
        expect_error="cas_action_cache_failure_ttl",
        label="a cached failure without an expiry is refused")
    run(uri, action(key=HEX2, status="FAILED", exit_code=1, failure_class="'CODE'",
                       expires="now() + interval '1 hour'"),
        label="a deterministic failure with a TTL is accepted")
    run(uri, action(key="c" * 64, risk="HIGH"),
        expect_error="cas_action_cache_high_risk_signed",
        label="an unsigned high-risk entry is refused")
    run(uri, action(key="c" * 64, risk="HIGH", key_id="'kms-1'", signature=f"'{HEX}'"),
        label="a signed high-risk entry is accepted")
    run(uri, action(key="d" * 64, image="'registry.internal/elmos/java21:latest'".strip("'")),
        expect_error="cas_action_cache_entries_toolchain_image_check",
        label="a mutable image tag is refused")
    run(uri, "UPDATE cas_action_cache_entries SET invalidated_at = now() WHERE action_key_hex = '"
                + HEX + "';",
        expect_error="cas_action_cache_invalidation_has_reason",
        label="invalidation without a reason is refused")
    run(uri, "UPDATE cas_action_cache_entries SET invalidated_at = now(),"
                " invalidation_reason = 'NODE_QUARANTINED' WHERE action_key_hex = '" + HEX + "';",
        label="invalidation with a reason is accepted")

    # --- upload sessions -------------------------------------------------------
    run(uri, "INSERT INTO cas_upload_sessions (organization_id, session_id, declared_size_bytes,"
                " chunk_size_bytes, session_state, deadline_at) VALUES ('org-a', 's1', 4096, 1024,"
                " 'OPEN', now() + interval '1 hour');", label="an open session is accepted")
    run(uri, "INSERT INTO cas_upload_sessions (organization_id, session_id, declared_size_bytes,"
                " chunk_size_bytes, session_state, deadline_at) VALUES ('org-a', 's2', 4096, 1024,"
                " 'OPEN', now() - interval '1 hour');",
        expect_error="cas_upload_sessions_deadline_after_creation",
        label="a session whose deadline already passed is refused")
    run(uri, "INSERT INTO cas_upload_sessions (organization_id, session_id, declared_size_bytes,"
                " chunk_size_bytes, session_state, deadline_at) VALUES ('org-a', 's3', 4096, 1024,"
                " 'QUARANTINED', now() + interval '1 hour');",
        expect_error="cas_upload_sessions_quarantine_state",
        label="a quarantined session without a quarantine id is refused")

    # --- append-only tables ----------------------------------------------------
    run(uri, f"INSERT INTO cas_deletion_manifests (organization_id, batch_id, dry_run,"
                f" collected_objects, retained_objects, reclaimed_bytes, manifest_digest_hex,"
                f" executed_by) VALUES ('org-a', 'batch-1', false, 3, 10, 4096, '{HEX}', 'gc');",
        label="a deletion manifest is written")
    run(uri, "UPDATE cas_deletion_manifests SET reclaimed_bytes = 0 WHERE batch_id = 'batch-1';",
        expect_error="append-only table", label="a deletion manifest cannot be edited")
    run(uri, "DELETE FROM cas_deletion_manifests WHERE batch_id = 'batch-1';",
        expect_error="append-only table", label="a deletion manifest cannot be deleted")
    run(uri, f"INSERT INTO cas_quarantine_events (organization_id, quarantine_id, subject_kind,"
                f" subject, detail) VALUES ('org-a', 'q-1', 'OBJECT', '{HEX}', 'digest mismatch');",
        expect_error="cas_quarantine_events_content_has_both_digests",
        label="a content quarantine without both digests is refused")
    run(uri, f"INSERT INTO cas_quarantine_events (organization_id, quarantine_id, subject_kind,"
                f" subject, declared_digest_hex, observed_digest_hex, detail)"
                f" VALUES ('org-a', 'q-1', 'OBJECT', '{HEX}', '{HEX}', '{HEX2}', 'digest mismatch');",
        label="a content quarantine with both digests is recorded")
    run(uri, f"INSERT INTO cas_quarantine_events (organization_id, quarantine_id, subject_kind,"
                f" subject, detail) VALUES ('org-a', 'q-2', 'NODE', 'ns/runners/sa/n1', 'nondeterminism');",
        label="a node quarantine needs no digests")

    # --- row level security ----------------------------------------------------
    run(uri, "CREATE ROLE elmos_app LOGIN", label="application role created")
    run(uri, "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO elmos_app",
        label="application role granted table access")
    def count_as(organization):
        with psycopg.connect(uri, autocommit=True) as connection:
            connection.execute("SET ROLE elmos_app")
            connection.execute("SELECT set_config('app.organization_id', %s, false)", (organization,))
            return connection.execute("SELECT count(*) FROM cas_object_catalog").fetchall()[0][0]

    def insert_as(organization, sql):
        with psycopg.connect(uri, autocommit=True) as connection:
            connection.execute("SET ROLE elmos_app")
            connection.execute("SELECT set_config('app.organization_id', %s, false)", (organization,))
            connection.execute(sql)

    isolated = count_as("org-b")
    checks += 1
    if isolated != 0:
        failures.append(f"RLS did not hide org-a rows from org-b: {isolated}")
    own = count_as("org-a")
    checks += 1
    if own != 2:
        failures.append(f"RLS hid org-a rows from org-a: expected 2, got {own}")

    checks += 1
    try:
        insert_as("org-b", "INSERT INTO cas_reference_roots (organization_id, root_kind, root_id,"
                           " digest_hex, size_bytes) VALUES ('org-a', 'SNAPSHOT', 'snap-1', '"
                           + HEX + "', 10)")
        failures.append("a tenant could write a row into another tenant")
    except psycopg.Error as error:
        if "row-level security" not in str(error):
            failures.append(f"cross-tenant write failed for the wrong reason: {error}")

    print(f"\nchecks executed: {checks}")
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for failure in failures:
            print("  -", failure)
        return 1
    print("all V65 constraints, indexes, triggers and policies behaved as specified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
