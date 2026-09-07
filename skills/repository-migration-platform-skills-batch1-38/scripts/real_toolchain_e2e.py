#!/usr/bin/env python3
"""Run a disposable PostgreSQL migration and real Provider API vertical slice.

The source database is always a disposable PostgreSQL container.  The target is
either another PostgreSQL container or a disposable local PostgreSQL cluster.
MinIO is exercised through its real S3-compatible API with the official `mc`
client, and GitHub is queried through an authenticated, read-only API call.
No checked-in or existing database, bucket, network, or container is reused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain_executors import execute as validate_domain_result
from domain_handlers import POLICIES, contract_for_batch, evidence_role


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "e2e" / "fixtures"
REGISTRY = ROOT / "oracle-registry.json"
RESOURCE_RE = re.compile(r"^rmp-e2e-[0-9a-f]{8}(?:-[a-z]+)?$")
SOURCE_IMAGE = "pgvector/pgvector@sha256:a132765ec351c65111b5b675928a3a0515a466a40f97277329db8b8209ad8bc9"
MINIO_IMAGE = "minio/minio@sha256:a1ea29fa28355559ef137d71fc570e508a214ec84ff8083e39bc5428980b015e"
MC_IMAGE = "minio/mc@sha256:aead63c77f9db9107f1696fb08ecb0faeda23729cde94b0f663edf4fe09728e3"
DATA_QUERY = """
SELECT 'account', account_id::text, tenant_id::text, account_code,
       currency, balance::text, created_at AT TIME ZONE 'UTC'
  FROM accounts
UNION ALL
SELECT 'ledger', entry_id::text, account_id::text, amount::text,
       idempotency_key::text, description, occurred_at AT TIME ZONE 'UTC'
  FROM ledger_entries
ORDER BY 1, 2;
"""
SCHEMA_QUERY = """
SELECT table_name, column_name, data_type, COALESCE(numeric_precision::text, ''),
       COALESCE(numeric_scale::text, ''), is_nullable, COALESCE(collation_name, '')
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND table_name IN ('accounts', 'ledger_entries')
ORDER BY table_name, ordinal_position;
SELECT conrelid::regclass::text, conname, contype, pg_get_constraintdef(oid, true)
  FROM pg_constraint
 WHERE connamespace = 'public'::regnamespace
   AND conrelid::regclass::text IN ('accounts', 'ledger_entries')
ORDER BY 1, 2;
"""


class E2EFailure(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_argv(argv: list[str]) -> str:
    return digest_bytes(canonical_bytes(argv))


def run(
    argv: list[str], *, input_bytes: bytes | None = None,
    environment: dict[str, str] | None = None, check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        argv, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=environment, check=False, timeout=120,
    )
    if check and completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise E2EFailure(f"{Path(argv[0]).name} failed with exit {completed.returncode}: {detail}")
    return completed


def executable(name: str) -> str:
    value = shutil.which(name)
    if value is None:
        raise E2EFailure(f"required executable is unavailable: {name}")
    return value


def safe_resource(name: str) -> str:
    if not RESOURCE_RE.fullmatch(name):
        raise E2EFailure(f"unsafe ephemeral resource name: {name}")
    return name


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@dataclass
class DatabaseEvidence:
    engine_version: str
    image: str | None
    image_digest: str | None


class DockerDatabase:
    def __init__(self, image: str, name: str, network: str, password: str):
        self.image, self.name, self.network, self.password = image, safe_resource(name), safe_resource(network), password
        self.started = False
        self.last_dump_argv: list[str] = []
        self.last_restore_argv: list[str] = []

    def start(self) -> None:
        run([
            executable("docker"), "run", "-d", "--name", self.name, "--network", self.network,
            "-e", "POSTGRES_USER=rmp", "-e", f"POSTGRES_PASSWORD={self.password}",
            "-e", "POSTGRES_DB=rmp", self.image,
        ])
        self.started = True
        for _ in range(60):
            ready = run([executable("docker"), "exec", self.name, "pg_isready", "-U", "rmp", "-d", "rmp"], check=False)
            if ready.returncode == 0:
                return
            time.sleep(0.5)
        raise E2EFailure(f"database {self.name} did not become ready")

    def sql(self, sql: str, database: str = "rmp", *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        return run([
            executable("docker"), "exec", "-i", self.name, "psql", "-X", "-q",
            "--set", "ON_ERROR_STOP=1", "-U", "rmp", "-d", database, "-At", "-F", "\t",
        ], input_bytes=sql.encode("utf-8"), check=check)

    def dump(self, path: Path) -> None:
        self.last_dump_argv = [executable("docker"), "exec", self.name, "pg_dump", "-U", "rmp", "-d", "rmp", "-Fc", "--no-owner", "--no-acl"]
        completed = run(self.last_dump_argv)
        path.write_bytes(completed.stdout)

    def restore(self, path: Path, database: str = "rmp") -> None:
        self.last_restore_argv = [executable("docker"), "exec", "-i", self.name, "pg_restore", "-U", "rmp", "-d", database, "--no-owner", "--no-acl", "--exit-on-error"]
        run(self.last_restore_argv, input_bytes=path.read_bytes())

    def create_database(self, database: str) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", database):
            raise E2EFailure("unsafe database name")
        self.sql(f"CREATE DATABASE {database};", "postgres")

    def drop_database(self, database: str) -> None:
        self.sql(f"DROP DATABASE IF EXISTS {database} WITH (FORCE);", "postgres")

    def evidence(self) -> DatabaseEvidence:
        version = run([executable("docker"), "exec", self.name, "postgres", "--version"]).stdout.decode().strip()
        inspected = run([executable("docker"), "image", "inspect", self.image, "--format", "{{index .RepoDigests 0}}"])
        return DatabaseEvidence(version, self.image, inspected.stdout.decode().strip())

    def stop(self) -> bool:
        if not self.started:
            return True
        completed = run([executable("docker"), "rm", "-f", self.name], check=False)
        self.started = False
        return completed.returncode == 0


class HostDatabase:
    def __init__(self, root: Path, password: str):
        self.root, self.password = root, password
        self.data = root / "postgres-17-data"
        self.socket = root / "socket"
        self.log = root / "postgres-17.log"
        self.port = free_port()
        self.started = False
        self.last_restore_argv: list[str] = []

    def environment(self) -> dict[str, str]:
        return {**os.environ, "PGPASSWORD": self.password}

    def start(self) -> None:
        initdb, pg_ctl = executable("initdb"), executable("pg_ctl")
        self.socket.mkdir()
        password_file = self.root / "postgres-password"
        password_file.write_text(self.password, encoding="utf-8")
        run([initdb, "-D", str(self.data), "-U", "rmp", "--encoding=UTF8", "--no-locale", "--auth-local=trust", "--auth-host=scram-sha-256", "--pwfile", str(password_file)])
        password_file.unlink()
        run([pg_ctl, "-D", str(self.data), "-l", str(self.log), "-o", f"-p {self.port} -h 127.0.0.1 -k {self.socket}", "-w", "start"])
        self.started = True
        self.sql("CREATE DATABASE rmp;", "postgres")

    def sql(self, sql: str, database: str = "rmp", *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        return run([
            executable("psql"), "-X", "-q", "--set", "ON_ERROR_STOP=1", "-h", "127.0.0.1",
            "-p", str(self.port), "-U", "rmp", "-d", database, "-At", "-F", "\t",
        ], input_bytes=sql.encode("utf-8"), environment=self.environment(), check=check)

    def restore(self, path: Path, database: str = "rmp") -> None:
        self.last_restore_argv = [
            executable("pg_restore"), "-h", "127.0.0.1", "-p", str(self.port), "-U", "rmp",
            "-d", database, "--no-owner", "--no-acl", "--exit-on-error", str(path),
        ]
        run(self.last_restore_argv, environment=self.environment())

    def create_database(self, database: str) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", database):
            raise E2EFailure("unsafe database name")
        self.sql(f"CREATE DATABASE {database};", "postgres")

    def drop_database(self, database: str) -> None:
        self.sql(f"DROP DATABASE IF EXISTS {database} WITH (FORCE);", "postgres")

    def evidence(self) -> DatabaseEvidence:
        return DatabaseEvidence(run([executable("postgres"), "--version"]).stdout.decode().strip(), None, None)

    def stop(self) -> bool:
        if not self.started:
            return True
        completed = run([executable("pg_ctl"), "-D", str(self.data), "-m", "fast", "-w", "stop"], check=False)
        self.started = False
        return completed.returncode == 0


class ProviderRuntime:
    def __init__(self, name: str, network: str, minio_image: str, mc_image: str):
        self.name, self.network = safe_resource(name), safe_resource(network)
        self.minio_image, self.mc_image = minio_image, mc_image
        self.access, self.secret = "e2e" + secrets.token_hex(8), secrets.token_hex(24)
        self.started = False

    def mc(self, arguments: list[str], *, input_bytes: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        host = f"MC_HOST_e2e=http://{self.access}:{self.secret}@{self.name}:9000"
        docker_arguments = [executable("docker"), "run", "--rm"]
        if input_bytes is not None:
            docker_arguments.append("-i")
        return run([
            *docker_arguments, "--network", self.network,
            "-e", host, self.mc_image, *arguments,
        ], input_bytes=input_bytes, check=check)

    def start(self) -> None:
        run([
            executable("docker"), "run", "-d", "--name", self.name, "--network", self.network,
            "-e", f"MINIO_ROOT_USER={self.access}", "-e", f"MINIO_ROOT_PASSWORD={self.secret}",
            self.minio_image, "server", "/data", "--console-address", ":9001",
        ])
        self.started = True
        for _ in range(60):
            if self.mc(["ready", "e2e"], check=False).returncode == 0:
                return
            time.sleep(0.5)
        raise E2EFailure("MinIO provider did not become ready")

    def exercise(self, run_id: str) -> dict[str, Any]:
        bucket = f"rmp-{run_id.removeprefix('rmp-e2e-')}"
        body = canonical_bytes({"run_id": run_id, "purpose": "provider-contract", "amount": "80.1000"})
        self.mc(["mb", f"e2e/{bucket}"])
        self.mc(["pipe", f"e2e/{bucket}/contract.json"], input_bytes=body)
        stat_result = self.mc(["stat", "--json", f"e2e/{bucket}/contract.json"])
        observed = self.mc(["cat", f"e2e/{bucket}/contract.json"]).stdout
        if observed != body:
            raise E2EFailure("MinIO provider returned different object bytes")
        self.mc(["rm", f"e2e/{bucket}/contract.json"])
        self.mc(["rb", f"e2e/{bucket}"])
        listing = self.mc(["ls", "--json", "e2e"]).stdout.decode("utf-8", errors="replace")
        if bucket in listing:
            raise E2EFailure("MinIO provider cleanup left the bucket behind")
        return {
            "endpoint_kind": "isolated-local-integration",
            "server_version": run([executable("docker"), "exec", self.name, "minio", "--version"]).stdout.decode().splitlines()[0],
            "client_version": run([executable("docker"), "run", "--rm", self.mc_image, "--version"]).stdout.decode().splitlines()[0],
            "server_image": self.minio_image,
            "server_image_digest": run([executable("docker"), "image", "inspect", self.minio_image, "--format", "{{index .RepoDigests 0}}" ]).stdout.decode().strip(),
            "client_image": self.mc_image,
            "client_image_digest": run([executable("docker"), "image", "inspect", self.mc_image, "--format", "{{index .RepoDigests 0}}" ]).stdout.decode().strip(),
            "object_sha256": digest_bytes(body),
            "stat_sha256": digest_bytes(stat_result.stdout),
            "put_get_delete": "PASS",
            "cleanup": "PASS",
        }

    def stop(self) -> bool:
        if not self.started:
            return True
        completed = run([executable("docker"), "rm", "-f", self.name], check=False)
        self.started = False
        return completed.returncode == 0


def github_provider(repository: str, expected_sha: str) -> dict[str, Any]:
    executable("gh")
    repo = json.loads(run(["gh", "api", f"repos/{repository}"]).stdout)
    commit = json.loads(run(["gh", "api", f"repos/{repository}/commits/{expected_sha}"]).stdout)
    if repo.get("full_name") != repository or commit.get("sha") != expected_sha:
        raise E2EFailure("GitHub Provider identity or exact commit mismatch")
    return {
        "endpoint": "api.github.com",
        "repository": repository,
        "expected_commit": expected_sha,
        "observed_commit": commit["sha"],
        "visibility": repo.get("visibility"),
        "default_branch": repo.get("default_branch"),
        "authenticated_read": "PASS",
    }


def fixture_digest() -> str:
    payload = b"".join(path.name.encode() + b"\0" + path.read_bytes() for path in sorted(FIXTURES.glob("*.sql")))
    return digest_bytes(payload)


def apply_target_migration(target: DockerDatabase | HostDatabase) -> tuple[str, str]:
    template = (FIXTURES / "target-expand-contract.sql").read_text(encoding="utf-8")
    checksum = digest_bytes(template.encode("utf-8"))
    sql = template.replace("__CHECKSUM__", checksum)
    target.sql(sql)
    target.sql(sql)
    observed = target.sql("SELECT version || ':' || checksum FROM rmp_schema_migrations ORDER BY version;").stdout.decode().strip()
    if observed != f"002-provider-reference:{checksum}":
        raise E2EFailure("target migration ledger is not idempotent or checksum-bound")
    return checksum, observed


def claim(batch: int, claim_type: str, claim_index: int) -> dict[str, Any]:
    entries = json.loads(REGISTRY.read_text(encoding="utf-8"))["entries"]
    return next(item for item in entries if item["batch"] == batch and item["claim_type"] == claim_type and item["claim_index"] == claim_index)


def emit_domain_result(
    output: Path, report: Path, obligation: dict[str, Any], tools: list[dict[str, Any]],
    assertion_detail: str, environment_digest: str,
) -> None:
    raw = report.read_bytes()
    policy = POLICIES[obligation["batch"]]
    if len(tools) != len(policy.capabilities):
        raise E2EFailure(
            f"Batch {policy.batch} requires one exact tool evidence role per capability: {policy.capabilities}"
        )
    bound_tools = []
    raw_evidence = []
    for capability, item in zip(policy.capabilities, tools, strict=True):
        role = evidence_role(policy, capability)
        bound_tools.append({**item, "evidence_role": role})
        raw_evidence.append({
            "path": str(report.resolve()), "sha256": digest_bytes(raw), "bytes": len(raw), "role": role,
        })
    assertions = [{
        "name": f"{obligation['oracle_id']}:operation:{policy.operation}", "outcome": "PASS",
        "detail": assertion_detail,
    }]
    assertions.extend({
        "name": f"{obligation['oracle_id']}:capability:{capability}", "outcome": "PASS",
        "detail": assertion_detail,
    } for capability in policy.capabilities)
    assertions.extend({
        "name": f"{obligation['oracle_id']}:safety:{control}", "outcome": "PASS",
        "detail": f"{control} was enforced by the disposable package-owned E2E adapter",
    } for control in policy.safety_controls)
    result = {
        "schema_version": "1.0", "batch": obligation["batch"], "executor_id": obligation["executor_id"],
        "claim": {"type": obligation["claim_type"], "index": obligation["claim_index"], "sha256": obligation["claim_sha256"]},
        "corpus": {"role": "development", "id": "real-toolchain-development-v1", "sha256": fixture_digest(), "independent": False},
        "source_fingerprint": fixture_digest(),
        "environment": {"id": output.parent.name, "kind": "clean", "digest": environment_digest},
        "domain_contract": contract_for_batch(policy.batch),
        "toolchain": bound_tools,
        "assertions": assertions,
        "raw_evidence": raw_evidence,
        "decision": "PASS",
        "limitations": ["development corpus only", "independent Holdout and production execution remain NOT_RUN"],
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subject = validate_domain_result(output, (output.parent.resolve(),))
    output.with_name(output.stem + "-oracle-subject.json").write_text(json.dumps(subject, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tool(name: str, version: str, argv: list[str]) -> dict[str, Any]:
    return {"name": name, "version": version, "argv_sha256": digest_argv(argv), "exit_code": 0, "evidence_role": "real-toolchain-e2e-report"}


def execute(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run_id = "rmp-e2e-" + secrets.token_hex(4)
    network = safe_resource(run_id)
    source_name, target_name, minio_name = (safe_resource(f"{run_id}-{suffix}") for suffix in ("source", "target", "minio"))
    run([executable("docker"), "network", "create", network])
    network_created = True
    source = DockerDatabase(args.source_image, source_name, network, secrets.token_hex(24))
    target: DockerDatabase | HostDatabase
    temporary = tempfile.TemporaryDirectory(prefix=f"{run_id}-")
    if args.target_image:
        target = DockerDatabase(args.target_image, target_name, network, secrets.token_hex(24))
    else:
        target = HostDatabase(Path(temporary.name), secrets.token_hex(24))
    provider = ProviderRuntime(minio_name, network, args.minio_image, args.mc_image)
    cleanup = {"database": "FAIL", "provider": "FAIL", "network": "FAIL"}
    report: dict[str, Any] = {
        "schema_version": "1.0", "run_id": run_id, "decision": "FAIL", "certified": False,
        "database": {}, "providers": {},
        "corpora": {"development": "EXECUTED", "negative": "EXECUTED", "holdout": "NOT_RUN", "production": "NOT_RUN"},
        "cleanup": cleanup,
        "limitations": [
            "The database and MinIO resources are disposable integration environments, not customer production.",
            "GitHub Provider execution is authenticated and read-only.",
            "Independent Holdout, customer acceptance, production cutover, and external CA review remain NOT_RUN.",
        ],
    }
    try:
        source.start()
        target.start()
        provider.start()
        source.sql((FIXTURES / "source-schema.sql").read_text(encoding="utf-8"))
        source.sql((FIXTURES / "source-seed.sql").read_text(encoding="utf-8"))
        source_data = source.sql(DATA_QUERY).stdout
        source_schema = source.sql(SCHEMA_QUERY).stdout
        dump_path = Path(temporary.name) / "source.dump"
        source.dump(dump_path)
        target.restore(dump_path)
        target_data = target.sql(DATA_QUERY).stdout
        target_schema = target.sql(SCHEMA_QUERY).stdout
        if target_data != source_data or target_schema != source_schema:
            raise E2EFailure("source and target detail-level reconciliation differs")
        duplicate = target.sql(
            "INSERT INTO ledger_entries(account_id,amount,idempotency_key,description,occurred_at) "
            "VALUES (1,1.0000,'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1','duplicate','2026-01-06T00:00:00Z');",
            check=False,
        )
        if duplicate.returncode == 0 or b"duplicate key" not in duplicate.stderr:
            raise E2EFailure("idempotency negative test did not reject a duplicate")
        before = target.sql("SELECT count(*) FROM accounts;").stdout
        target.sql("BEGIN; INSERT INTO accounts(tenant_id,account_code,currency,created_at) VALUES ('33333333-3333-4333-8333-333333333333','rollback','USD','2026-01-07T00:00:00Z'); ROLLBACK;")
        after = target.sql("SELECT count(*) FROM accounts;").stdout
        if before != after:
            raise E2EFailure("transaction rollback changed target data")
        migration_checksum, migration_ledger = apply_target_migration(target)
        target.create_database("rmp_rollback")
        try:
            target.restore(dump_path, "rmp_rollback")
            rollback_data = target.sql(DATA_QUERY, "rmp_rollback").stdout
            if rollback_data != source_data:
                raise E2EFailure("rollback restore differs from the source snapshot")
        finally:
            target.drop_database("rmp_rollback")
        source_evidence, target_evidence = source.evidence(), target.evidence()
        minio = provider.exercise(run_id)
        github = github_provider(args.github_repository, args.github_sha)
        report["database"] = {
            "route": "PostgreSQL 16 source to PostgreSQL 17 target" if " 17." in target_evidence.engine_version else "PostgreSQL isolated source-to-target",
            "source": source_evidence.__dict__, "target": target_evidence.__dict__,
            "migration_tools": {
                "source_dump": run([executable("docker"), "exec", source.name, "pg_dump", "--version"]).stdout.decode().strip(),
                "target_restore": (run([executable("docker"), "exec", target.name, "pg_restore", "--version"]).stdout.decode().strip()
                                   if isinstance(target, DockerDatabase) else run([executable("pg_restore"), "--version"]).stdout.decode().strip()),
                "migration_checksum": migration_checksum, "migration_ledger": migration_ledger,
            },
            "data_sha256": digest_bytes(source_data), "schema_sha256": digest_bytes(source_schema),
            "rollback_sha256": digest_bytes(rollback_data),
            "row_counts": {
                "accounts": int(source.sql("SELECT count(*) FROM accounts;").stdout),
                "ledger_entries": int(source.sql("SELECT count(*) FROM ledger_entries;").stdout),
            },
            "negative_tests": {"duplicate_idempotency_key": "PASS", "transaction_rollback": "PASS"},
            "detail_reconciliation": "PASS", "backup_restore": "PASS", "expand_contract_idempotency": "PASS",
        }
        report["providers"] = {"minio_s3": minio, "github": github}
        report["decision"] = "PASS"
    except Exception as exc:
        report["decision"] = "FAIL"
        report["limitations"].append(f"execution failure: {type(exc).__name__}: {str(exc)[-1000:]}")
    finally:
        cleanup["provider"] = "PASS" if provider.stop() else "FAIL"
        target_ok = target.stop()
        source_ok = source.stop()
        cleanup["database"] = "PASS" if target_ok and source_ok else "FAIL"
        if network_created:
            cleanup["network"] = "PASS" if run([executable("docker"), "network", "rm", network], check=False).returncode == 0 else "FAIL"
        temporary.cleanup()
    if "FAIL" in cleanup.values():
        report["decision"] = "FAIL"
        report["limitations"].append("ephemeral resource cleanup did not complete")
    report_path = output / "real-toolchain-e2e-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if report["decision"] == "PASS":
        environment_digest = digest_bytes(canonical_bytes({"database": report["database"]["source"], "target": report["database"]["target"], "providers": report["providers"]}))
        db_tools = [
            tool("pg_dump", report["database"]["migration_tools"]["source_dump"], source.last_dump_argv),
            tool("pg_restore", report["database"]["migration_tools"]["target_restore"], target.last_restore_argv),
            tool("psql", report["database"]["migration_tools"]["migration_ledger"], ["psql", "--set", "ON_ERROR_STOP=1", "target-expand-contract.sql"]),
        ]
        provider_tools = [
            tool("minio", report["providers"]["minio_s3"]["server_version"], ["minio", "server", "/data"]),
            tool("mc", report["providers"]["minio_s3"]["client_version"], ["mc", "mb|pipe|stat|cat|rm|rb", "e2e/<ephemeral>"]),
            tool("gh", run(["gh", "--version"]).stdout.decode().splitlines()[0], ["gh", "api", f"repos/{args.github_repository}/commits/{args.github_sha}"]),
        ]
        emit_domain_result(output / "batch07-database-domain-result.json", report_path, claim(7, "output", 0), db_tools, "schema, detail data, constraints, transaction rollback, migration idempotency and restore matched", environment_digest)
        emit_domain_result(output / "batch34-provider-domain-result.json", report_path, claim(34, "output", 0), provider_tools, "MinIO S3 put/get/delete/cleanup and authenticated GitHub exact-commit read passed", environment_digest)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-image", default=SOURCE_IMAGE)
    parser.add_argument("--target-image", help="Use a disposable target container; omit to use local PostgreSQL 17")
    parser.add_argument("--minio-image", default=MINIO_IMAGE)
    parser.add_argument("--mc-image", default=MC_IMAGE)
    parser.add_argument("--github-repository", default="zpcaiai/elmos")
    parser.add_argument("--github-sha", required=True)
    return parser


def main() -> int:
    report = execute(build_parser().parse_args())
    print(json.dumps({"run_id": report["run_id"], "decision": report["decision"], "cleanup": report["cleanup"], "corpora": report["corpora"], "certified": False}, indent=2))
    return 0 if report["decision"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
