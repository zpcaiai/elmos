from __future__ import annotations

from typing import Any

from .container_images import MYSQL_IMAGE, POSTGRES_IMAGE
from .models import EntitySpec, FieldSpec, SynthesisRequest
from .rendering import clean, pretty_json


def _sql_type(field: FieldSpec, is_sqlite: bool = False) -> str:
    if is_sqlite:
        return {
            "string": "TEXT",
            "integer": "INTEGER",
            "number": "REAL",
            "boolean": "INTEGER",
            "datetime": "TEXT",
        }[field.type]
    return {
        "string": "text",
        "integer": "bigint",
        "number": "numeric(20,6)",
        "boolean": "boolean",
        "datetime": "timestamptz",
    }[field.type]


def _mysql_sql_type(field: FieldSpec) -> str:
    return {
        "string": "VARCHAR(255)",
        "integer": "BIGINT",
        "number": "DECIMAL(20,6)",
        "boolean": "TINYINT(1)",
        "datetime": "DATETIME(6)",
    }[field.type]


def _table(entity: EntitySpec) -> str:
    return entity.plural


def _comparison_sql(rule: dict[str, Any]) -> str | None:
    predicate = rule.get("predicate")
    if not isinstance(predicate, dict) or predicate.get("type") != "field-comparison":
        return None
    operator_name = predicate.get("operator")
    if not isinstance(operator_name, str):
        return None
    operator = {
        "gte": ">=",
        "gt": ">",
        "lte": "<=",
        "lt": "<",
        "eq": "=",
        "neq": "<>",
    }.get(operator_name)
    value = predicate.get("value")
    if operator is None or not isinstance(value, int | float | bool | str):
        return None
    literal = (
        "TRUE"
        if value is True
        else "FALSE"
        if value is False
        else str(value)
        if isinstance(value, int | float)
        else "'" + value.replace("'", "''") + "'"
    )
    return f'CONSTRAINT "{rule["id"].lower()}_check" CHECK ("{predicate["field"]}" {operator} {literal})'


def _mysql_comparison_sql(rule: dict[str, Any]) -> str | None:
    predicate = rule.get("predicate")
    if not isinstance(predicate, dict) or predicate.get("type") != "field-comparison":
        return None
    operator_name = predicate.get("operator")
    if not isinstance(operator_name, str):
        return None
    operator = {
        "gte": ">=",
        "gt": ">",
        "lte": "<=",
        "lt": "<",
        "eq": "=",
        "neq": "<>",
    }.get(operator_name)
    value = predicate.get("value")
    if operator is None or not isinstance(value, int | float | bool | str):
        return None
    literal = (
        "TRUE"
        if value is True
        else "FALSE"
        if value is False
        else str(value)
        if isinstance(value, int | float)
        else "'" + value.replace("'", "''") + "'"
    )
    return f'CONSTRAINT `{rule["id"].lower()}_check` CHECK (`{predicate["field"]}` {operator} {literal})'


def _sqlite_schema_sql(request: SynthesisRequest) -> str:
    blocks = [
        "-- Generated from an approved ELMOS baseline. Forward-only migration.",
        "PRAGMA foreign_keys = ON;",
        "BEGIN TRANSACTION;",
    ]
    uuid_relation_fields = {
        (relation.source, relation.source_field)
        for relation in request.canonical_relations
        if relation.source_field is not None and relation.target_field == "id"
    }
    for entity in request.entities:
        columns = [
            '"tenant_id" TEXT NOT NULL',
            '"id" TEXT NOT NULL',
            *[
                (
                    f'"{field.name}" '
                    f"{'TEXT' if (entity.singular, field.name) in uuid_relation_fields else _sql_type(field, True)}"
                    f"{' NOT NULL' if field.required else ''}"
                )
                for field in entity.fields
            ],
            'CONSTRAINT "tenant_id_not_blank" CHECK (length(trim("tenant_id")) > 0)',
            f'CONSTRAINT "pk_{entity.singular}" PRIMARY KEY ("tenant_id", "id")',
        ]
        for rule in request.raw["business_rules"]:
            predicate = rule.get("predicate")
            if isinstance(predicate, dict) and predicate.get("entity") == entity.singular:
                check = _comparison_sql(rule)
                if check:
                    columns.append(check)
        for relation in request.canonical_relations:
            if relation.source != entity.singular or relation.source_field is None or relation.target_field is None:
                continue
            target_table = _table(next(e for e in request.entities if e.singular == relation.target))
            fk_constraint = (
                f'CONSTRAINT "fk_{relation.source}_{relation.source_field}_{relation.target}" '
                f'FOREIGN KEY ("tenant_id", "{relation.source_field}") '
                f'REFERENCES "{target_table}" ("tenant_id", "{relation.target_field}") '
                "ON UPDATE CASCADE ON DELETE RESTRICT"
            )
            columns.append(fk_constraint)
            if relation.enforces_uniqueness:
                uq_constraint = (
                    f'CONSTRAINT "uq_{relation.source}_{relation.source_field}" '
                    f'UNIQUE ("tenant_id", "{relation.source_field}")'
                )
                columns.append(uq_constraint)
        table = _table(entity)
        blocks.extend(
            [
                f'CREATE TABLE IF NOT EXISTS "{table}" (',
                "  " + ",\n  ".join(columns),
                ");",
                f'CREATE INDEX IF NOT EXISTS "idx_{table}_tenant" ON "{table}" ("tenant_id");',
            ]
        )
    blocks.extend(
        [
            "CREATE TABLE IF NOT EXISTS schema_migrations (",
            "  version TEXT PRIMARY KEY,",
            "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))",
            ");",
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES ('001_initial');",
            "COMMIT;",
        ]
    )
    return "\n".join(blocks) + "\n"


def _mysql_schema_sql(request: SynthesisRequest) -> str:
    blocks = [
        "-- Generated from an approved ELMOS baseline. Forward-only migration.",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 1;",
    ]
    uuid_relation_fields = {
        (relation.source, relation.source_field)
        for relation in request.canonical_relations
        if relation.source_field is not None and relation.target_field == "id"
    }
    for entity in request.entities:
        field_col_defs = []
        for field in entity.fields:
            if (entity.singular, field.name) in uuid_relation_fields:
                col_type = "VARCHAR(36)"
            else:
                col_type = _mysql_sql_type(field)
            nullable = " NOT NULL" if field.required else ""
            field_col_defs.append(f"`{field.name}` {col_type}{nullable}")

        columns = [
            "`tenant_id` VARCHAR(64) NOT NULL",
            "`id` VARCHAR(36) NOT NULL",
            *field_col_defs,
            "CONSTRAINT `tenant_id_not_blank` CHECK (CHAR_LENGTH(TRIM(`tenant_id`)) > 0)",
            "PRIMARY KEY (`tenant_id`, `id`)",
        ]
        for rule in request.raw["business_rules"]:
            predicate = rule.get("predicate")
            if isinstance(predicate, dict) and predicate.get("entity") == entity.singular:
                check = _mysql_comparison_sql(rule)
                if check:
                    columns.append(check)
        for relation in request.canonical_relations:
            if relation.source != entity.singular or relation.source_field is None or relation.target_field is None:
                continue
            target_table = _table(next(e for e in request.entities if e.singular == relation.target))
            fk_constraint = (
                f"CONSTRAINT `fk_{relation.source}_{relation.source_field}_{relation.target}` "
                f"FOREIGN KEY (`tenant_id`, `{relation.source_field}`) "
                f"REFERENCES `{target_table}` (`tenant_id`, `{relation.target_field}`) "
                "ON UPDATE CASCADE ON DELETE RESTRICT"
            )
            columns.append(fk_constraint)
            if relation.enforces_uniqueness:
                uq_constraint = (
                    f"CONSTRAINT `uq_{relation.source}_{relation.source_field}` "
                    f"UNIQUE KEY (`tenant_id`, `{relation.source_field}`)"
                )
                columns.append(uq_constraint)
        table = _table(entity)
        blocks.extend(
            [
                f"CREATE TABLE IF NOT EXISTS `{table}` (",
                "  " + ",\n  ".join(columns),
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
                f"CREATE INDEX `idx_{table}_tenant` ON `{table}` (`tenant_id`);",
            ]
        )
    blocks.extend(
        [
            "CREATE TABLE IF NOT EXISTS `schema_migrations` (",
            "  `version` VARCHAR(64) PRIMARY KEY,",
            "  `applied_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)",
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
            "INSERT IGNORE INTO `schema_migrations` (`version`) VALUES ('001_initial');",
        ]
    )
    return "\n".join(blocks) + "\n"


def _schema_sql(request: SynthesisRequest) -> str:
    if request.is_sqlite:
        return _sqlite_schema_sql(request)
    if request.is_mysql:
        return _mysql_schema_sql(request)
    blocks = [
        "-- Generated from an approved ELMOS baseline. Forward-only migration.",
        "BEGIN;",
        "CREATE SCHEMA IF NOT EXISTS app;",
    ]
    uuid_relation_fields = {
        (relation.source, relation.source_field)
        for relation in request.canonical_relations
        if relation.source_field is not None and relation.target_field == "id"
    }
    for entity in request.entities:
        columns = [
            '"tenant_id" text NOT NULL',
            '"id" uuid NOT NULL',
            *[
                f'"{field.name}" '
                f"{'uuid' if (entity.singular, field.name) in uuid_relation_fields else _sql_type(field)}"
                f"{' NOT NULL' if field.required else ''}"
                for field in entity.fields
            ],
            'CONSTRAINT "tenant_id_not_blank" CHECK (length(btrim("tenant_id")) > 0)',
            f'CONSTRAINT "pk_{entity.singular}" PRIMARY KEY ("tenant_id", "id")',
        ]
        for rule in request.raw["business_rules"]:
            predicate = rule.get("predicate")
            if isinstance(predicate, dict) and predicate.get("entity") == entity.singular:
                check = _comparison_sql(rule)
                if check:
                    columns.append(check)
        table = _table(entity)
        blocks.extend(
            [
                f'CREATE TABLE IF NOT EXISTS "app"."{table}" (',
                "  " + ",\n  ".join(columns),
                ");",
                f'CREATE INDEX IF NOT EXISTS "idx_{table}_tenant" ON "app"."{table}" ("tenant_id");',
                f'ALTER TABLE "app"."{table}" ENABLE ROW LEVEL SECURITY;',
                f'ALTER TABLE "app"."{table}" FORCE ROW LEVEL SECURITY;',
                f'DROP POLICY IF EXISTS "tenant_isolation" ON "app"."{table}";',
                f'CREATE POLICY "tenant_isolation" ON "app"."{table}"',
                "  USING (tenant_id = current_setting('app.tenant_id', true))",
                "  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));",
            ]
        )
    for relation in request.canonical_relations:
        if relation.source_field is None or relation.target_field is None:
            continue
        source_table = _table(next(entity for entity in request.entities if entity.singular == relation.source))
        target_table = _table(next(entity for entity in request.entities if entity.singular == relation.target))
        constraint = f"fk_{relation.source}_{relation.source_field}_{relation.target}"
        blocks.extend(
            [
                f'ALTER TABLE "app"."{source_table}" DROP CONSTRAINT IF EXISTS "{constraint}";',
                f'ALTER TABLE "app"."{source_table}" ADD CONSTRAINT "{constraint}"',
                f'  FOREIGN KEY ("tenant_id", "{relation.source_field}")',
                f'  REFERENCES "app"."{target_table}" ("tenant_id", "{relation.target_field}")',
                "  ON UPDATE CASCADE ON DELETE RESTRICT;",
            ]
        )
        if relation.enforces_uniqueness:
            # This is the whole difference between one-to-one and many-to-one:
            # the same foreign key, forbidden to repeat. Scoped by tenant_id,
            # like every other constraint in this schema.
            unique = f"uq_{relation.source}_{relation.source_field}"
            blocks.extend(
                [
                    f'ALTER TABLE "app"."{source_table}" DROP CONSTRAINT IF EXISTS "{unique}";',
                    f'ALTER TABLE "app"."{source_table}" ADD CONSTRAINT "{unique}"',
                    f'  UNIQUE ("tenant_id", "{relation.source_field}");',
                ]
            )
    blocks.extend(
        [
            "CREATE TABLE IF NOT EXISTS app.schema_migrations (",
            "  version text PRIMARY KEY,",
            "  applied_at timestamptz NOT NULL DEFAULT now()",
            ");",
            "INSERT INTO app.schema_migrations(version) VALUES ('001_initial')",
            "ON CONFLICT (version) DO NOTHING;",
            "COMMIT;",
        ]
    )
    return "\n".join(blocks) + "\n"


def _policy_contract(request: SynthesisRequest) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "default_decision": "deny",
        "identity": {
            "mode": request.auth_mode,
            "subject_claim": "sub",
            "tenant_claim": "tenant_id",
            "role_claim": "roles",
            "issuer_env": "ELMOS_AUTH_ISSUER",
            "audience_env": "ELMOS_AUTH_AUDIENCE",
            "jwt_hmac_secret_file_env": "ELMOS_JWT_HMAC_SECRET_FILE",
            "oidc_jwks_file_env": "ELMOS_OIDC_JWKS_FILE",
        },
        "permissions": request.raw["permissions"],
        "business_rules": request.raw["business_rules"],
        "negative_requirements": [
            "missing or malformed bearer token is denied",
            "missing tenant claim is denied",
            "tenant claim is never accepted from a client-controlled tenant header",
            "deny decisions override allow decisions",
            "unknown actor, action, or resource is denied",
        ],
    }


def _secret_contract(request: SynthesisRequest) -> dict[str, Any]:
    references = [
        {
            "name": "database-url",
            "required": request.requires_database,
            "file_env": "ELMOS_DATABASE_URL_FILE",
            "minimum_permissions": "0400",
            "value_must_not_appear_in": ["source", "environment-dump", "logs", "evidence", "artifacts"],
        },
        {
            "name": "jwt-hmac-secret",
            "required": request.auth_mode == "jwt",
            "file_env": "ELMOS_JWT_HMAC_SECRET_FILE",
            "minimum_bytes": 32,
            "minimum_permissions": "0400",
            "value_must_not_appear_in": ["source", "environment-dump", "logs", "evidence", "artifacts"],
        },
    ]
    if request.auth_mode == "oidc":
        references.append(
            {
                "name": "oidc-jwks",
                "required": True,
                "file_env": "ELMOS_OIDC_JWKS_FILE",
                "minimum_permissions": "0400",
                "refresh": "externally-managed-atomic-file-replacement",
                "network_policy": "application-default-deny",
            }
        )
    return {
        "schema_version": "1.0.0",
        "provider": "external-secret-reference",
        "rotation": {"required": True, "application_restart": False},
        "references": references,
    }


def _observability(request: SynthesisRequest) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "service": request.project_name,
        "logs": {
            "implementation_status": "GENERATED",
            "format": "json",
            "required_fields": ["timestamp", "level", "service", "request_id", "route", "status"],
            "forbidden_fields": ["authorization", "cookie", "token", "secret", "database_url"],
            "tenant_field": "tenant_hash",
        },
        "metrics": {
            "implementation_status": "GENERATED",
            "endpoint": "/metrics",
            "required": [
                "http_server_requests_total",
                "http_server_request_duration_seconds",
                "authz_denied_total",
                "database_operation_duration_seconds",
            ],
            "forbidden_labels": ["subject", "email", "raw_tenant_id", "token"],
        },
        "tracing": {
            "protocol": "OTLP",
            "endpoint_env": "OTEL_EXPORTER_OTLP_ENDPOINT",
            "sampling_env": "OTEL_TRACES_SAMPLER_ARG",
            "implementation_status": "NOT_RUN",
        },
        "health": {
            "liveness": "/health/live",
            "readiness": "/health/ready",
            "dependency_checks_only_in_readiness": True,
        },
    }


def _slo(request: SynthesisRequest) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "service": request.project_name,
        "window": "30d",
        "objectives": [
            {
                "id": "availability",
                "indicator": "successful non-health requests / valid non-health requests",
                "target": 0.999,
                "owner": "service-owner",
            },
            {
                "id": "latency",
                "indicator": "p95 request duration",
                "target": "<=300ms",
                "owner": "service-owner",
            },
        ],
        "burn_rate_alerts": [
            {"window": "1h", "burn_rate": 14.4, "severity": "page", "runbook": "operations/runbook.md"},
            {"window": "6h", "burn_rate": 6, "severity": "ticket", "runbook": "operations/runbook.md"},
        ],
        "alert_delivery_status": "NOT_RUN",
        "status": "DEFINED_NOT_EVIDENCED",
    }


def render_production_assets(request: SynthesisRequest) -> dict[str, str]:
    if request.is_sqlite:
        backup_sh = clean(
            """
            #!/bin/sh
            set -eu
            umask 077
            : "${ELMOS_DATABASE_URL_FILE:?ELMOS_DATABASE_URL_FILE is required}"
            : "${ELMOS_BACKUP_OUTPUT:?ELMOS_BACKUP_OUTPUT is required}"
            test -f "$ELMOS_DATABASE_URL_FILE"
            test ! -e "$ELMOS_BACKUP_OUTPUT"
            DB_PATH="$(cat "$ELMOS_DATABASE_URL_FILE" | sed -e 's|^sqlite://||')"
            sqlite3 "$DB_PATH" ".backup '$ELMOS_BACKUP_OUTPUT'"
            sha256sum "$ELMOS_BACKUP_OUTPUT" > "$ELMOS_BACKUP_OUTPUT.sha256"
            """
        )
        restore_sh = clean(
            """
            #!/bin/sh
            set -eu
            umask 077
            : "${ELMOS_RESTORE_DATABASE_URL_FILE:?ELMOS_RESTORE_DATABASE_URL_FILE is required}"
            : "${ELMOS_BACKUP_INPUT:?ELMOS_BACKUP_INPUT is required}"
            test -f "$ELMOS_RESTORE_DATABASE_URL_FILE"
            test -f "$ELMOS_BACKUP_INPUT"
            test -f "$ELMOS_BACKUP_INPUT.sha256"
            sha256sum -c "$ELMOS_BACKUP_INPUT.sha256"
            RESTORE_PATH="$(cat "$ELMOS_RESTORE_DATABASE_URL_FILE" | sed -e 's|^sqlite://||')"
            cp "$ELMOS_BACKUP_INPUT" "$RESTORE_PATH"
            """
        )
    elif request.is_mysql:
        backup_sh = clean(
            """
            #!/bin/sh
            set -eu
            umask 077
            : "${ELMOS_DATABASE_URL_FILE:?ELMOS_DATABASE_URL_FILE is required}"
            : "${ELMOS_BACKUP_OUTPUT:?ELMOS_BACKUP_OUTPUT is required}"
            test -f "$ELMOS_DATABASE_URL_FILE"
            test ! -e "$ELMOS_BACKUP_OUTPUT"
            python3 -c "
            import subprocess, sys, urllib.parse
            url = open(sys.argv[1], encoding='utf-8').read().strip()
            p = urllib.parse.urlsplit(url)
            cmd = ['mysqldump', '-h', p.hostname or '127.0.0.1', '-P', str(p.port or 3306), '-u', p.username or 'root']
            if p.password:
                cmd.append(f'-p{p.password}')
            cmd.extend(['--single-transaction', '--quick', f'--result-file={sys.argv[2]}', p.path.lstrip('/')])
            subprocess.run(cmd, check=True)
            " "$ELMOS_DATABASE_URL_FILE" "$ELMOS_BACKUP_OUTPUT"
            sha256sum "$ELMOS_BACKUP_OUTPUT" > "$ELMOS_BACKUP_OUTPUT.sha256"
            """
        )
        restore_sh = clean(
            """
            #!/bin/sh
            set -eu
            umask 077
            : "${ELMOS_RESTORE_DATABASE_URL_FILE:?ELMOS_RESTORE_DATABASE_URL_FILE is required}"
            : "${ELMOS_BACKUP_INPUT:?ELMOS_BACKUP_INPUT is required}"
            test -f "$ELMOS_RESTORE_DATABASE_URL_FILE"
            test -f "$ELMOS_BACKUP_INPUT"
            test -f "$ELMOS_BACKUP_INPUT.sha256"
            sha256sum -c "$ELMOS_BACKUP_INPUT.sha256"
            python3 -c "
            import subprocess, sys, urllib.parse
            url = open(sys.argv[1], encoding='utf-8').read().strip()
            p = urllib.parse.urlsplit(url)
            cmd = ['mysql', '-h', p.hostname or '127.0.0.1', '-P', str(p.port or 3306), '-u', p.username or 'root']
            if p.password:
                cmd.append(f'-p{p.password}')
            cmd.append(p.path.lstrip('/'))
            with open(sys.argv[2], 'rb') as stream:
                subprocess.run(cmd, stdin=stream, check=True)
            " "$ELMOS_RESTORE_DATABASE_URL_FILE" "$ELMOS_BACKUP_INPUT"
            """
        )
    else:
        backup_sh = clean(
            """
            #!/bin/sh
            set -eu
            umask 077
            : "${ELMOS_DATABASE_URL_FILE:?ELMOS_DATABASE_URL_FILE is required}"
            : "${ELMOS_BACKUP_OUTPUT:?ELMOS_BACKUP_OUTPUT is required}"
            test -f "$ELMOS_DATABASE_URL_FILE"
            test ! -e "$ELMOS_BACKUP_OUTPUT"
            pg_dump --dbname="$(cat "$ELMOS_DATABASE_URL_FILE")" \\
              --format=custom --no-owner --no-privileges --file="$ELMOS_BACKUP_OUTPUT"
            sha256sum "$ELMOS_BACKUP_OUTPUT" > "$ELMOS_BACKUP_OUTPUT.sha256"
            """
        )
        restore_sh = clean(
            """
            #!/bin/sh
            set -eu
            umask 077
            : "${ELMOS_RESTORE_DATABASE_URL_FILE:?ELMOS_RESTORE_DATABASE_URL_FILE is required}"
            : "${ELMOS_BACKUP_INPUT:?ELMOS_BACKUP_INPUT is required}"
            test -f "$ELMOS_RESTORE_DATABASE_URL_FILE"
            test -f "$ELMOS_BACKUP_INPUT"
            test -f "$ELMOS_BACKUP_INPUT.sha256"
            sha256sum -c "$ELMOS_BACKUP_INPUT.sha256"
            pg_restore --dbname="$(cat "$ELMOS_RESTORE_DATABASE_URL_FILE")" \\
              --exit-on-error --no-owner --no-privileges "$ELMOS_BACKUP_INPUT"
            """
        )

    files = {
        "security/policy-contract.json": pretty_json(_policy_contract(request)),
        "security/secret-contract.json": pretty_json(_secret_contract(request)),
        "observability/observability-contract.json": pretty_json(_observability(request)),
        "operations/slo-contract.json": pretty_json(_slo(request)),
        "operations/runbook.md": clean(
            f"""
            # {request.project_name} operations runbook

            ## Deploy

            Resolve every secret reference, apply database migrations with a
            migration identity, deploy one immutable image digest, wait for
            readiness, then run the authenticated tenant-isolation journey.

            ## Rollback and forward recovery

            Application images are rollback-safe only while the database
            compatibility gate permits mixed versions. Database migrations are
            forward-only. When a migration is not backward compatible, stop
            rollout and use an approved forward-recovery migration.

            ## Backup and restore

            {
                "Backups use `sqlite3 .backup` against the live SQLite database file. "
                "Restore by validating the checksum and atomic copy into the target path."
                if request.is_sqlite
                else
                "Backups use `mysqldump --single-transaction --quick` against a consistent snapshot. "
                "Restore into a new database, run migrations, verify row counts and tenant-isolation negatives, "
                "then switch traffic through an approved change. Never overwrite the only existing database."
                if request.is_mysql
                else
                "Backups use `pg_dump --format=custom` against a read-consistent "
                "snapshot. Restore into a new database, run migrations, verify row "
                "counts and tenant-isolation negatives, then switch traffic through "
                "an approved change. Never overwrite the only existing database."
            }

            RPO, RTO, restore, failover, and external alert delivery remain
            `NOT_RUN` until their authorized exercises produce digested
            evidence.
            """
        ),
        "operations/backup.sh": backup_sh,
        "operations/restore.sh": restore_sh,
    }
    if request.requires_database:
        if request.is_sqlite:
            apply_migrations = clean(
                """
                #!/bin/sh
                set -eu
                umask 077
                : "${ELMOS_DATABASE_URL_FILE:?ELMOS_DATABASE_URL_FILE is required}"
                test -f "$ELMOS_DATABASE_URL_FILE"
                DB_PATH="$(cat "$ELMOS_DATABASE_URL_FILE" | sed -e 's|^sqlite://||')"
                sqlite3 "$DB_PATH" < "$(dirname "$0")/migrations/001_initial.sql"
                """
            )
        elif request.is_mysql:
            apply_migrations = clean(
                """
                #!/bin/sh
                set -eu
                umask 077
                : "${ELMOS_DATABASE_URL_FILE:?ELMOS_DATABASE_URL_FILE is required}"
                test -f "$ELMOS_DATABASE_URL_FILE"
                python3 -c "
                import subprocess, sys, urllib.parse
                url = open(sys.argv[1], encoding='utf-8').read().strip()
                p = urllib.parse.urlsplit(url)
                cmd = ['mysql', '-h', p.hostname or '127.0.0.1', '-P', str(p.port or 3306), '-u', p.username or 'root']
                if p.password:
                    cmd.append(f'-p{p.password}')
                cmd.append(p.path.lstrip('/'))
                with open(sys.argv[2], 'rb') as stream:
                    subprocess.run(cmd, stdin=stream, check=True)
                " "$ELMOS_DATABASE_URL_FILE" "$(dirname "$0")/migrations/001_initial.sql"
                """
            )
        else:
            apply_migrations = clean(
                """
                #!/bin/sh
                set -eu
                umask 077
                : "${ELMOS_DATABASE_URL_FILE:?ELMOS_DATABASE_URL_FILE is required}"
                test -f "$ELMOS_DATABASE_URL_FILE"
                psql --set=ON_ERROR_STOP=1 \\
                  --dbname="$(cat "$ELMOS_DATABASE_URL_FILE")" \\
                  --file="$(dirname "$0")/migrations/001_initial.sql"
                """
            )
        files.update(
            {
                "database/migrations/001_initial.sql": _schema_sql(request),
                "database/migrations/manifest.json": pretty_json(
                    {
                        "schema_version": "1.0.0",
                        "provider": "sqlite" if request.is_sqlite else ("mysql" if request.is_mysql else "postgresql"),
                        "provider_version": "3.45" if request.is_sqlite else ("8.0" if request.is_mysql else "17.5"),
                        "strategy": "forward-only",
                        "migrations": [
                            {
                                "version": "001_initial",
                                "path": "database/migrations/001_initial.sql",
                                "recovery": "forward-fix-or-restore-into-new-database",
                            }
                        ],
                        "runtime_evidence": "NOT_RUN",
                    }
                ),
                "database/apply-migrations.sh": apply_migrations,
            }
        )
        if request.is_postgresql:
            files["database/postgres-image.txt"] = f"{POSTGRES_IMAGE}\n"
        elif request.is_mysql:
            files["database/mysql-image.txt"] = f"{MYSQL_IMAGE}\n"
    return files
