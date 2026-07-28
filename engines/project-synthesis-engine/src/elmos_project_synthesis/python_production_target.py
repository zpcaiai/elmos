# ruff: noqa: S608
# This deterministic generator accepts SQL identifiers only through the strict
# lower-case entity/field contract; emitted runtime values remain parameterized.
from __future__ import annotations

import json

from .container_images import POSTGRES_IMAGE, PYTHON_IMAGE
from .models import EntitySpec, FieldSpec, SynthesisRequest, pascal
from .rendering import (
    clean,
    dockerignore,
    env_example,
    gitignore,
    kubernetes_yaml,
    openapi_yaml,
    sample_payload,
    target_readme,
)


def _python_type(field: FieldSpec) -> str:
    return {
        "string": "str",
        "integer": "int",
        "number": "Decimal",
        "boolean": "bool",
        "datetime": "datetime",
    }[field.type]


def _production_model_field(
    request: SynthesisRequest,
    *,
    entity: str,
    field: FieldSpec,
) -> tuple[str, bool]:
    constraints: dict[str, int | float] = {}
    if field.type in {"integer", "number"}:
        names = {"gte": "ge", "gt": "gt", "lte": "le", "lt": "lt"}
        for rule in request.raw["business_rules"]:
            predicate = rule.get("predicate")
            if (
                isinstance(predicate, dict)
                and predicate.get("type") == "field-comparison"
                and predicate.get("entity") == entity
                and predicate.get("field") == field.name
                and predicate.get("operator") in names
                and isinstance(predicate.get("value"), int | float)
            ):
                constraints[names[str(predicate["operator"])]] = predicate["value"]
    relation_targets_id = any(
        relation.source == entity and relation.source_field == field.name and relation.target_field == "id"
        for relation in request.relations
    )
    type_name = "UUID" if relation_targets_id else _python_type(field)
    if constraints:
        arguments = ", ".join(f"{name}={value!r}" for name, value in sorted(constraints.items()))
        if field.required:
            return f"    {field.name}: {type_name} = Field({arguments})", True
        return f"    {field.name}: {type_name} | None = Field(default=None, {arguments})", True
    return (
        f"    {field.name}: {type_name}{'' if field.required else ' | None = None'}",
        False,
    )


def _wrapped_python_string(value: str, *, body_indent: int, closing_indent: int) -> str:
    chunks = [value[index : index + 72] for index in range(0, len(value), 72)] or [""]
    body = "\n".join(" " * body_indent + json.dumps(chunk) for chunk in chunks)
    return "(\n" + body + "\n" + " " * closing_indent + ")"


def _integration_fixture_lines(request: SynthesisRequest, entity: EntitySpec) -> list[str]:
    lines = ["payload = " + repr(sample_payload(request, entity))]
    fixture_ids: set[str] = set()
    visiting: set[str] = set()

    def add_dependencies(entity_name: str) -> None:
        if entity_name in visiting:
            raise ValueError("PRODUCTION_RELATION_CYCLE")
        visiting.add(entity_name)
        for relation in request.relations:
            if relation.source != entity_name or relation.source_field is None:
                continue
            if relation.target in fixture_ids:
                continue
            add_dependencies(relation.target)
            target = next(item for item in request.entities if item.singular == relation.target)
            payload_name = f"{target.singular}_fixture_payload"
            lines.append(f"{payload_name} = {sample_payload(request, target)!r}")
            for target_relation in request.relations:
                if target_relation.source == target.singular and target_relation.source_field is not None:
                    lines.append(
                        f'{payload_name}["{target_relation.source_field}"] = {target_relation.target}_fixture_id'
                    )
            lines.extend(
                [
                    f"{target.singular}_fixture = client.post(",
                    f'    "/api/v1/{target.plural}",',
                    f"    json={payload_name},",
                    '    headers={"Authorization": f"Bearer {token_a}"},',
                    ")",
                    f"assert {target.singular}_fixture.status_code == 201",
                    f'{target.singular}_fixture_id = {target.singular}_fixture.json()["id"]',
                ]
            )
            fixture_ids.add(target.singular)
        visiting.remove(entity_name)

    add_dependencies(entity.singular)
    for relation in request.relations:
        if relation.source == entity.singular and relation.source_field is not None:
            lines.append(f'payload["{relation.source_field}"] = {relation.target}_fixture_id')
    return lines


def _integration_roles(request: SynthesisRequest) -> list[str]:
    """Bind the integration identity to the approved permission matrix."""

    operations = {
        (entity.singular, action)
        for entity in request.entities
        for action in ("create", "read", "update", "delete")
    }
    permissions = request.raw["permissions"]
    actors = sorted({str(permission["actor"]) for permission in permissions})

    def covers(permission: dict[str, object], resource: str, action: str) -> bool:
        return permission["resource"] in {resource, "*"} and permission["action"] in {
            action,
            "manage",
        }

    eligible = [
        actor
        for actor in actors
        if not any(
            permission["actor"] == actor
            and permission["effect"] == "deny"
            and any(covers(permission, resource, action) for resource, action in operations)
            for permission in permissions
        )
    ]
    covered = {
        (resource, action)
        for resource, action in operations
        if any(
            permission["actor"] in eligible
            and permission["effect"] == "allow"
            and covers(permission, resource, action)
            for permission in permissions
        )
    }
    missing = sorted(operations - covered)
    if missing:
        detail = ",".join(f"{resource}:{action}" for resource, action in missing)
        raise ValueError(f"PRODUCTION_INTEGRATION_IDENTITY_UNSATISFIABLE:{detail}")
    return eligible


def _security_source(request: SynthesisRequest) -> str:
    permissions = json.dumps(request.raw["permissions"], ensure_ascii=False, indent=4, sort_keys=True)
    permissions = permissions.replace("\n", "\n        ")
    unverified_header = "unverified = jwt.get_unverified_header(encoded)" if request.auth_mode == "oidc" else ""
    auth_setup = (
        clean(
            """
            jwks = json.loads(_secret_file("ELMOS_OIDC_JWKS_FILE", minimum=1))
            key_id = unverified.get("kid")
            matching = [item for item in jwks.get("keys", []) if item.get("kid") == key_id]
            if len(matching) != 1:
                raise HTTPException(status_code=401, detail="signing key is unavailable")
            key = jwt.PyJWK.from_dict(matching[0]).key
            algorithms = ["RS256", "ES256"]
            """
        )
        if request.auth_mode == "oidc"
        else clean(
            """
            key = _secret_file("ELMOS_JWT_HMAC_SECRET_FILE", minimum=32)
            algorithms = ["HS256"]
            """
        )
    )
    auth_setup = auth_setup.rstrip().replace("\n", "\n                ")
    return clean(
        f"""
        from __future__ import annotations

        import json
        import os
        import re
        import stat
        from collections.abc import Callable
        from dataclasses import dataclass
        from pathlib import Path
        from typing import Annotated

        import jwt
        from fastapi import Header, HTTPException

        from .telemetry import AUTHENTICATION_FAILED, AUTHORIZATION_DENIED

        _TENANT = re.compile(r"^[a-z][a-z0-9-]{{2,62}}$")
        _PERMISSIONS = {permissions}


        @dataclass(frozen=True)
        class Identity:
            subject: str
            tenant_id: str
            roles: frozenset[str]


        def _secret_file(environment_key: str, *, minimum: int) -> str:
            raw_path = os.getenv(environment_key, "")
            path = Path(raw_path)
            if not raw_path or not path.is_absolute() or path.is_symlink():
                raise RuntimeError(f"{{environment_key}}_INVALID")
            details = path.stat()
            if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
                raise RuntimeError(f"{{environment_key}}_UNSAFE")
            value = path.read_text(encoding="utf-8").strip()
            if len(value.encode("utf-8")) < minimum or len(value) > 65536:
                raise RuntimeError(f"{{environment_key}}_INVALID")
            return value


        def identity_from_authorization(authorization: Annotated[str | None, Header()] = None) -> Identity:
            if authorization is None or not authorization.startswith("Bearer "):
                AUTHENTICATION_FAILED.inc()
                raise HTTPException(status_code=401, detail="bearer authentication required")
            encoded = authorization.removeprefix("Bearer ").strip()
            if not encoded or len(encoded) > 16384:
                AUTHENTICATION_FAILED.inc()
                raise HTTPException(status_code=401, detail="bearer authentication required")
            issuer = os.getenv("ELMOS_AUTH_ISSUER", "")
            audience = os.getenv("ELMOS_AUTH_AUDIENCE", "")
            if not issuer or not audience:
                AUTHENTICATION_FAILED.inc()
                raise HTTPException(status_code=503, detail="identity provider is not configured")
            try:
                {unverified_header}
                {auth_setup}
                claims = jwt.decode(
                    encoded,
                    key,
                    algorithms=algorithms,
                    audience=audience,
                    issuer=issuer,
                    options={{"require": ["exp", "iat", "iss", "aud", "sub", "tenant_id", "roles"]}},
                )
            except (OSError, RuntimeError, jwt.PyJWTError, ValueError, json.JSONDecodeError) as error:
                AUTHENTICATION_FAILED.inc()
                raise HTTPException(status_code=401, detail="token validation failed") from error
            subject = claims.get("sub")
            tenant_id = claims.get("tenant_id")
            roles = claims.get("roles")
            if (
                not isinstance(subject, str)
                or not subject
                or not isinstance(tenant_id, str)
                or not _TENANT.fullmatch(tenant_id)
                or not isinstance(roles, list)
                or not roles
                or not all(isinstance(role, str) and role for role in roles)
            ):
                AUTHENTICATION_FAILED.inc()
                raise HTTPException(status_code=401, detail="required identity claims are invalid")
            return Identity(subject=subject, tenant_id=tenant_id, roles=frozenset(roles))


        def authorize(resource: str, action: str) -> Callable[[str | None], Identity]:
            def dependency(authorization: Annotated[str | None, Header()] = None) -> Identity:
                identity = identity_from_authorization(authorization)
                decisions = [
                    item["effect"]
                    for item in _PERMISSIONS
                    if item["actor"] in identity.roles
                    and item["resource"] in {{resource, "*"}}
                    and item["action"] in {{action, "manage"}}
                ]
                if "deny" in decisions or "allow" not in decisions:
                    AUTHORIZATION_DENIED.labels(resource=resource, action=action).inc()
                    raise HTTPException(status_code=403, detail="authorization denied")
                return identity

            return dependency
        """
    )


def _test_identity_source(auth_mode: str) -> str:
    if auth_mode == "jwt":
        imports = "import secrets"
        body = clean(
            """
            secret_file = output / "jwt-hmac"
            secret_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
            secret_file.chmod(0o600)
            """
        )
    else:
        imports = clean(
            """
            import json

            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from jwt.algorithms import RSAAlgorithm
            """
        ).rstrip()
        body = clean(
            """
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            private_file = output / "oidc-private-key.pem"
            private_file.write_bytes(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
            public_jwk["kid"] = "elmos-local-integration"
            jwks_file = output / "oidc-jwks.json"
            jwks_file.write_text(
                json.dumps({"keys": [public_jwk]}, sort_keys=True),
                encoding="utf-8",
            )
            private_file.chmod(0o600)
            jwks_file.chmod(0o600)
            """
        )
    imports = imports.replace("\n", "\n        ")
    body = body.rstrip().replace("\n", "\n            ")
    return clean(
        f"""
        from __future__ import annotations

        {imports}
        import sys
        from pathlib import Path


        def main() -> int:
            if len(sys.argv) != 2:
                raise RuntimeError("TEST_IDENTITY_OUTPUT_REQUIRED")
            output = Path(sys.argv[1]).resolve()
            if output.exists() or output.is_symlink():
                raise RuntimeError("TEST_IDENTITY_OUTPUT_MUST_NOT_EXIST")
            output.mkdir(mode=0o700)
            {body}
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        """
    )


def _ci_workflow(auth_mode: str) -> str:
    auth_environment = (
        "ELMOS_JWT_HMAC_SECRET_FILE: /tmp/elmos-test-identity/jwt-hmac"
        if auth_mode == "jwt"
        else (
            "ELMOS_OIDC_JWKS_FILE: /tmp/elmos-test-identity/oidc-jwks.json\n"
            "ELMOS_OIDC_PRIVATE_KEY_FILE: /tmp/elmos-test-identity/oidc-private-key.pem"
        )
    )
    auth_environment = auth_environment.replace("\n", "\n                  ")
    write_admin_url = (
        "printf '%s' 'postgresql://postgres:integration-only@127.0.0.1:5432/generated' > /tmp/admin-database-url"
    )
    create_runtime_role = (
        'psql "$(cat /tmp/admin-database-url)" --set=ON_ERROR_STOP=1 --command '
        "\"CREATE ROLE app_runtime LOGIN PASSWORD 'integration-runtime-only' "
        'NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"'
    )
    grant_runtime_role = (
        'psql "$(cat /tmp/admin-database-url)" --set=ON_ERROR_STOP=1 --command '
        '"GRANT USAGE ON SCHEMA app TO app_runtime; '
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_runtime"'
    )
    write_runtime_url = (
        "printf '%s' 'postgresql://app_runtime:integration-runtime-only@127.0.0.1:5432/generated' > /tmp/database-url"
    )
    return clean(
        f"""
        name: python-production-profile
        on: [push, pull_request]
        permissions:
          contents: read
        jobs:
          test:
            runs-on: ubuntu-latest
            defaults:
              run:
                working-directory: python
            services:
              postgres:
                image: {POSTGRES_IMAGE}
                env:
                  POSTGRES_PASSWORD: integration-only
                  POSTGRES_DB: generated
                ports: ["5432:5432"]
                options: >-
                  --health-cmd "pg_isready -U postgres -d generated"
                  --health-interval 5s --health-timeout 3s --health-retries 20
            steps:
              - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
              - uses: astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e # v6
              - run: uv lock --check
              - run: uv sync --locked --python 3.12
              - run: uv run python scripts/create-test-identity.py /tmp/elmos-test-identity
              - run: |
                  umask 077
                  {write_admin_url}
                  ELMOS_DATABASE_URL_FILE=/tmp/admin-database-url ../database/apply-migrations.sh
                  {create_runtime_role}
                  {grant_runtime_role}
                  {write_runtime_url}
              - run: uv run pytest -m integration
                env:
                  ELMOS_DATABASE_URL_FILE: /tmp/database-url
                  {auth_environment}
                  ELMOS_AUTH_ISSUER: https://identity.test.invalid/
                  ELMOS_AUTH_AUDIENCE: generated-api
              - run: uv run pytest -m "not integration"
              - run: uv run ruff check src tests scripts
              - run: uv run mypy src
        """
    )


def _local_runtime_source(package_name: str, auth_mode: str) -> str:
    if auth_mode == "jwt":
        runtime_auth_imports = "import secrets"
        runtime_auth_setup = clean(
            """
            jwt_secret_file = state / "jwt-hmac"
            if not jwt_secret_file.exists():
                jwt_secret_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
                jwt_secret_file.chmod(0o600)
            if jwt_secret_file.is_symlink() or jwt_secret_file.stat().st_mode & 0o077:
                raise RuntimeError("LOCAL_JWT_SECRET_FILE_UNSAFE")
            environment["ELMOS_JWT_HMAC_SECRET_FILE"] = str(jwt_secret_file)
            """
        )
    else:
        runtime_auth_imports = clean(
            """
            import json

            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from jwt.algorithms import RSAAlgorithm
            """
        )
        runtime_auth_setup = clean(
            """
            oidc_private_key_file = state / "oidc-private-key.pem"
            oidc_jwks_file = state / "oidc-jwks.json"
            if oidc_private_key_file.exists() != oidc_jwks_file.exists():
                raise RuntimeError("LOCAL_OIDC_KEYSET_INCOMPLETE")
            if not oidc_private_key_file.exists():
                private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                oidc_private_key_file.write_bytes(
                    private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                )
                public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
                public_jwk["kid"] = "elmos-local-integration"
                oidc_jwks_file.write_text(
                    json.dumps({"keys": [public_jwk]}, sort_keys=True),
                    encoding="utf-8",
                )
                oidc_private_key_file.chmod(0o600)
                oidc_jwks_file.chmod(0o600)
            if (
                oidc_private_key_file.is_symlink()
                or oidc_jwks_file.is_symlink()
                or oidc_private_key_file.stat().st_mode & 0o077
                or oidc_jwks_file.stat().st_mode & 0o077
            ):
                raise RuntimeError("LOCAL_OIDC_KEYSET_UNSAFE")
            environment["ELMOS_OIDC_JWKS_FILE"] = str(oidc_jwks_file)
            environment["ELMOS_OIDC_PRIVATE_KEY_FILE"] = str(oidc_private_key_file)
            """
        )
    runtime_auth_imports = runtime_auth_imports.rstrip().replace("\n", "\n        ")
    runtime_auth_setup = runtime_auth_setup.rstrip().replace("\n", "\n            ")
    return clean(
        f"""
        from __future__ import annotations

        import atexit
        import os
        {runtime_auth_imports}
        import shutil
        import signal
        import subprocess
        import sys
        import tempfile
        import time
        from pathlib import Path

        EXPECTED_POSTGRES_VERSIONS = {{
            "postgres (PostgreSQL) 17.5",
            "postgres (PostgreSQL) 17.5 (Homebrew)",
        }}
        children: list[subprocess.Popen[bytes]] = []
        stopping = False
        runtime_socket: Path | None = None


        def required_tool(name: str) -> Path:
            candidate = shutil.which(name)
            if candidate is not None:
                return Path(candidate).resolve()
            fallback = Path("/opt/homebrew/opt/postgresql@17/bin") / name
            if fallback.is_file():
                return fallback
            raise RuntimeError(f"REQUIRED_TOOL_NOT_FOUND:{{name}}")


        def run(command: list[str], *, environment: dict[str, str] | None = None) -> None:
            subprocess.run(command, check=True, env=environment)


        def cleanup_runtime_socket() -> None:
            global runtime_socket
            temporary_root = Path(tempfile.gettempdir()).resolve()
            if (
                runtime_socket is not None
                and runtime_socket.parent == temporary_root
                and runtime_socket.name.startswith("elmos-pg-")
            ):
                try:
                    shutil.rmtree(runtime_socket)
                except FileNotFoundError:
                    pass
                runtime_socket = None


        def stop_children(*_: object) -> None:
            global stopping
            if stopping:
                cleanup_runtime_socket()
                return
            stopping = True
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
            deadline = time.monotonic() + 8
            for child in reversed(children):
                try:
                    child.wait(timeout=max(0.1, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2)
            cleanup_runtime_socket()


        def main() -> int:
            global runtime_socket
            atexit.register(stop_children)
            signal.signal(signal.SIGTERM, stop_children)
            signal.signal(signal.SIGINT, stop_children)
            workspace = Path.cwd().resolve()
            state = Path(os.getenv("ELMOS_RUNTIME_STATE_DIR", ".elmos-runtime")).resolve()
            if state == workspace or workspace not in state.parents or state.is_symlink():
                raise RuntimeError("RUNTIME_STATE_DIRECTORY_MUST_BE_WORKSPACE_CONFINED")
            state.mkdir(parents=True, exist_ok=True, mode=0o700)
            data = state / "postgres-data"
            temporary_root = Path(tempfile.gettempdir()).resolve()
            socket = Path(tempfile.mkdtemp(prefix="elmos-pg-", dir=temporary_root)).resolve()
            if socket.parent != temporary_root or not socket.name.startswith("elmos-pg-"):
                raise RuntimeError("POSTGRES_SOCKET_DIRECTORY_INVALID")
            socket.chmod(0o700)
            runtime_socket = socket

            postgres = required_tool("postgres")
            observed = subprocess.run(
                [str(postgres), "--version"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            if observed not in EXPECTED_POSTGRES_VERSIONS:
                raise RuntimeError(
                    "POSTGRES_VERSION_MISMATCH:"
                    f"expected={{sorted(EXPECTED_POSTGRES_VERSIONS)}}:observed={{observed}}"
                )
            binaries = postgres.parent
            if not data.exists():
                run(
                    [
                        str(binaries / "initdb"),
                        "--pgdata",
                        str(data),
                        "--auth-local=trust",
                        "--auth-host=reject",
                        "--encoding=UTF8",
                        "--no-locale",
                    ]
                )

            database = subprocess.Popen(
                [
                    str(postgres),
                    "-D",
                    str(data),
                    "-k",
                    str(socket),
                    "-h",
                    "",
                    "-c",
                    "fsync=on",
                    "-c",
                    "synchronous_commit=on",
                ]
            )
            children.append(database)
            for _ in range(100):
                if database.poll() is not None:
                    raise RuntimeError("POSTGRES_START_FAILED")
                ready = subprocess.run(
                    [str(binaries / "pg_isready"), "-h", str(socket)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("POSTGRES_START_TIMEOUT")

            created = subprocess.run(
                [str(binaries / "createdb"), "-h", str(socket), "app_db"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            if created.returncode != 0 and "already exists" not in created.stderr:
                raise RuntimeError("POSTGRES_DATABASE_CREATE_FAILED")
            role_sql = (
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN "
                "CREATE ROLE app_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
                "END IF; END $$;"
            )
            psql = str(binaries / "psql")
            run([psql, "-h", str(socket), "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", role_sql])
            migration = workspace.parent / "database" / "migrations" / "001_initial.sql"
            run([psql, "-h", str(socket), "-d", "app_db", "-v", "ON_ERROR_STOP=1", "-f", str(migration)])
            grants = (
                "GRANT USAGE ON SCHEMA app TO app_runtime; "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_runtime; "
                "ALTER DEFAULT PRIVILEGES IN SCHEMA app "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_runtime;"
            )
            run([psql, "-h", str(socket), "-d", "app_db", "-v", "ON_ERROR_STOP=1", "-c", grants])
            database_url_file = state / "database-url"
            database_url_file.write_text(
                f"postgresql://app_runtime@/app_db?host={{socket}}",
                encoding="utf-8",
            )
            database_url_file.chmod(0o600)
            environment = dict(os.environ)
            environment["ELMOS_DATABASE_URL_FILE"] = str(database_url_file)
            environment["ELMOS_AUTH_ISSUER"] = "https://identity.local.invalid/"
            environment["ELMOS_AUTH_AUDIENCE"] = "generated-api"
            {runtime_auth_setup}
            if sys.argv[1:] == ["--verify"]:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-m", "integration"],
                    check=False,
                    env=environment,
                )
                stop_children()
                return result.returncode
            if sys.argv[1:]:
                raise RuntimeError("LOCAL_RUNTIME_ARGUMENT_INVALID")
            app = subprocess.Popen([sys.executable, "-m", "{package_name}"], env=environment)
            children.append(app)
            return_code = app.wait()
            stop_children()
            return return_code


        if __name__ == "__main__":
            raise SystemExit(main())
        """
    )


def render_python_production(request: SynthesisRequest, port: int) -> dict[str, str]:
    package_name = request.project_name.replace("-", "_")
    model_blocks: list[str] = []
    repository_blocks: list[str] = []
    route_blocks: list[str] = []
    integration_tests: list[str] = []
    integration_roles = json.dumps(
        _integration_roles(request),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    model_imports: list[str] = []
    uses_pydantic_field = False
    if request.auth_mode == "jwt":
        integration_signing_setup = clean(
            """
            signing_key = Path(os.environ["ELMOS_JWT_HMAC_SECRET_FILE"]).read_text(encoding="utf-8").strip()
            algorithm = "HS256"
            headers = None
            """
        )
    else:
        integration_signing_setup = clean(
            """
            signing_key = Path(os.environ["ELMOS_OIDC_PRIVATE_KEY_FILE"]).read_bytes()
            algorithm = "RS256"
            headers = {"kid": "elmos-local-integration"}
            """
        )
    integration_signing_setup = integration_signing_setup.rstrip().replace("\n", "\n                ")
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        upsert_class = f"{entity_class}Upsert"
        model_imports.extend((entity_class, upsert_class))
        field_declarations = [
            _production_model_field(
                request,
                entity=entity.singular,
                field=field,
            )
            for field in entity.fields
        ]
        field_lines = [declaration for declaration, _ in field_declarations]
        uses_pydantic_field = uses_pydantic_field or any(uses_field for _, uses_field in field_declarations)
        model_blocks.append(
            f"class {upsert_class}(BaseModel):\n"
            '    model_config = ConfigDict(extra="forbid")\n\n'
            + "\n".join(field_lines)
            + f"\n\n\nclass {entity_class}({upsert_class}):\n    id: UUID"
        )
        columns = [field.name for field in entity.fields]
        quoted_columns = ", ".join(f'"{column}"' for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        values = ", ".join(f"payload.{column}" for column in columns)
        assignments = ", ".join(f'"{column}" = EXCLUDED."{column}"' for column in columns)
        list_query = (  # noqa: S608 - identifiers are produced by strict entity/field validators.
            f'SELECT "id", {quoted_columns} FROM "app"."{entity.plural}" ORDER BY "id"'
        )
        get_query = (  # noqa: S608 - identifiers are produced by strict entity/field validators.
            f'SELECT "id", {quoted_columns} FROM "app"."{entity.plural}" WHERE "id" = %s'
        )
        save_query = (  # noqa: S608 - identifiers are produced by strict entity/field validators.
            f'INSERT INTO "app"."{entity.plural}" '
            f'("tenant_id", "id", {quoted_columns}) VALUES (%s, %s, {placeholders}) '
            f'ON CONFLICT ("tenant_id", "id") DO UPDATE SET {assignments} '
            f'RETURNING "id", {quoted_columns}'
        )
        delete_query = (  # noqa: S608 - identifiers are produced by strict entity/field validators.
            f'DELETE FROM "app"."{entity.plural}" WHERE "id" = %s'
        )
        repository_blocks.append(
            clean(
                f"""
                def _{entity.singular}_from_row(row: dict[str, object]) -> {entity_class}:
                    return {entity_class}.model_validate(row)


                def list_{entity.plural}(identity: Identity) -> list[{entity_class}]:
                    with tenant_connection(identity.tenant_id) as connection:
                        query = {_wrapped_python_string(list_query, body_indent=24, closing_indent=20)}
                        rows = connection.execute(query).fetchall()
                    return [_{entity.singular}_from_row(dict(row)) for row in rows]


                def get_{entity.singular}(identity: Identity, record_id: UUID) -> {entity_class} | None:
                    with tenant_connection(identity.tenant_id) as connection:
                        query = {_wrapped_python_string(get_query, body_indent=24, closing_indent=20)}
                        row = connection.execute(query, (str(record_id),)).fetchone()
                    return None if row is None else _{entity.singular}_from_row(dict(row))


                def save_{entity.singular}(
                    identity: Identity,
                    record_id: UUID,
                    payload: {upsert_class},
                ) -> {entity_class}:
                    with tenant_connection(identity.tenant_id) as connection:
                        query = {_wrapped_python_string(save_query, body_indent=24, closing_indent=20)}
                        row = connection.execute(
                            query,
                            (identity.tenant_id, str(record_id), {values}),
                        ).fetchone()
                    assert row is not None
                    return _{entity.singular}_from_row(dict(row))


                def delete_{entity.singular}(identity: Identity, record_id: UUID) -> bool:
                    with tenant_connection(identity.tenant_id) as connection:
                        query = {_wrapped_python_string(delete_query, body_indent=24, closing_indent=20)}
                        result = connection.execute(query, (str(record_id),))
                    return result.rowcount == 1
                """
            ).rstrip()
        )
        route_blocks.append(
            clean(
                f"""
                @app.get("/api/v1/{entity.plural}", response_model=list[{entity_class}])
                def list_{entity.plural}(
                    identity: Annotated[Identity, Depends(authorize("{entity.singular}", "read"))],
                ) -> list[{entity_class}]:
                    return repository.list_{entity.plural}(identity)


                @app.get("/api/v1/{entity.plural}/{{record_id}}", response_model={entity_class})
                def get_{entity.singular}(
                    record_id: UUID,
                    identity: Annotated[Identity, Depends(authorize("{entity.singular}", "read"))],
                ) -> {entity_class}:
                    record = repository.get_{entity.singular}(identity, record_id)
                    if record is None:
                        raise HTTPException(status_code=404, detail="record not found")
                    return record


                @app.post("/api/v1/{entity.plural}", response_model={entity_class}, status_code=201)
                def create_{entity.singular}(
                    payload: {upsert_class},
                    identity: Annotated[Identity, Depends(authorize("{entity.singular}", "create"))],
                ) -> {entity_class}:
                    return repository.save_{entity.singular}(identity, uuid4(), payload)


                @app.put("/api/v1/{entity.plural}/{{record_id}}", response_model={entity_class})
                def update_{entity.singular}(
                    record_id: UUID,
                    payload: {upsert_class},
                    identity: Annotated[Identity, Depends(authorize("{entity.singular}", "update"))],
                ) -> {entity_class}:
                    if repository.get_{entity.singular}(identity, record_id) is None:
                        raise HTTPException(status_code=404, detail="record not found")
                    return repository.save_{entity.singular}(identity, record_id, payload)


                @app.delete("/api/v1/{entity.plural}/{{record_id}}", status_code=204)
                def delete_{entity.singular}(
                    record_id: UUID,
                    identity: Annotated[Identity, Depends(authorize("{entity.singular}", "delete"))],
                ) -> Response:
                    if not repository.delete_{entity.singular}(identity, record_id):
                        raise HTTPException(status_code=404, detail="record not found")
                    return Response(status_code=204)
                """
            ).rstrip()
        )
        fixture_lines = _integration_fixture_lines(request, entity)
        fixture_source = "\n".join(fixture_lines).replace("\n", "\n                    ")
        integration_tests.append(
            clean(
                f"""
                def test_{entity.singular}_tenant_isolation_and_crud() -> None:
                    token_a = token("tenant-a")
                    token_b = token("tenant-b")
                    {fixture_source}
                    created = client.post(
                        "/api/v1/{entity.plural}",
                        json=payload,
                        headers={{"Authorization": f"Bearer {{token_a}}"}},
                    )
                    assert created.status_code == 201
                    record_id = created.json()["id"]
                    assert client.get(
                        f"/api/v1/{entity.plural}/{{record_id}}",
                        headers={{"Authorization": f"Bearer {{token_a}}"}},
                    ).status_code == 200
                    assert client.get(
                        f"/api/v1/{entity.plural}/{{record_id}}",
                        headers={{"Authorization": f"Bearer {{token_b}}"}},
                    ).status_code == 404
                    listed = client.get(
                        "/api/v1/{entity.plural}",
                        headers={{"Authorization": f"Bearer {{token_a}}"}},
                    )
                    assert listed.status_code == 200
                    assert record_id in {{item["id"] for item in listed.json()}}
                    assert client.put(
                        f"/api/v1/{entity.plural}/{{record_id}}",
                        json=payload,
                        headers={{"Authorization": f"Bearer {{token_b}}"}},
                    ).status_code == 404
                    assert client.put(
                        f"/api/v1/{entity.plural}/{{record_id}}",
                        json=payload,
                        headers={{"Authorization": f"Bearer {{token_a}}"}},
                    ).status_code == 200
                    assert client.delete(
                        f"/api/v1/{entity.plural}/{{record_id}}",
                        headers={{"Authorization": f"Bearer {{token_b}}"}},
                    ).status_code == 404
                    assert client.delete(
                        f"/api/v1/{entity.plural}/{{record_id}}",
                        headers={{"Authorization": f"Bearer {{token_a}}"}},
                    ).status_code == 204
                    assert client.get(
                        f"/api/v1/{entity.plural}/{{record_id}}",
                        headers={{"Authorization": f"Bearer {{token_a}}"}},
                    ).status_code == 404
                """
            ).rstrip()
        )
    model_import_lines = ["from uuid import UUID"]
    if any(field.type == "datetime" for entity in request.entities for field in entity.fields):
        model_import_lines.append("from datetime import datetime")
    if any(field.type == "number" for entity in request.entities for field in entity.fields):
        model_import_lines.append("from decimal import Decimal")
    model_imports_source = "\n".join(sorted(model_import_lines)) + "\n"
    pydantic_imports = "BaseModel, ConfigDict, Field" if uses_pydantic_field else "BaseModel, ConfigDict"
    dependencies = [
        "fastapi==0.116.1",
        "prometheus-client==0.22.1",
        "psycopg[binary]==3.2.9",
        "pydantic==2.11.7",
        "PyJWT[crypto]==2.10.1",
        "uvicorn==0.35.0",
    ]
    healthcheck = f"import urllib.request; urllib.request.urlopen('http://127.0.0.1:{port}/health/live', timeout=1)"
    repository_source = "\n\n".join(repository_blocks).replace("\n", "\n            ")
    route_source = "\n\n".join(route_blocks).replace("\n", "\n            ")
    integration_test_source = "\n\n".join(integration_tests).replace("\n", "\n            ")
    return {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port)
        + clean(
            """
            ELMOS_DATABASE_URL_FILE=/run/secrets/database-url
            ELMOS_AUTH_ISSUER=https://identity.example.invalid/
            ELMOS_AUTH_AUDIENCE=generated-api
            ELMOS_JWT_HMAC_SECRET_FILE=/run/secrets/jwt-hmac
            ELMOS_OIDC_JWKS_FILE=/run/secrets/oidc-jwks
            """
        ),
        "pyproject.toml": clean(
            f"""
            [project]
            name = "{request.project_name}"
            version = "1.0.0"
            description = {json.dumps(request.description, ensure_ascii=False)}
            requires-python = ">=3.12,<3.13"
            dependencies = {json.dumps(dependencies, indent=2)}

            [dependency-groups]
            dev = [
              "httpx==0.28.1",
              "mypy==1.17.0",
              "pytest==8.4.1",
              "ruff==0.12.5",
            ]

            [build-system]
            requires = ["hatchling==1.27.0"]
            build-backend = "hatchling.build"

            [tool.hatch.build.targets.wheel]
            packages = ["src/{package_name}"]

            [tool.pytest.ini_options]
            addopts = "-q --strict-markers -m 'not integration'"
            testpaths = ["tests"]
            markers = ["integration: requires the exact PostgreSQL profile"]

            [tool.ruff]
            target-version = "py312"
            line-length = 120

            [tool.ruff.lint]
            select = ["E", "F", "I", "B", "UP", "S"]
            ignore = ["S101", "S603"]

            [tool.mypy]
            python_version = "3.12"
            strict = true
            packages = ["{package_name}"]
            """
        ),
        f"src/{package_name}/__init__.py": f'"""Production profile for {request.project_name}."""\n',
        f"src/{package_name}/models.py": clean(model_imports_source + f"\nfrom pydantic import {pydantic_imports}\n")
        + "\n\n"
        + "\n\n".join(model_blocks)
        + "\n",
        f"src/{package_name}/telemetry.py": clean(
            """
            from prometheus_client import Counter, Histogram

            HTTP_REQUESTS = Counter(
                "http_server_requests_total",
                "HTTP requests by method, normalized route, and status.",
                ("method", "route", "status"),
            )
            HTTP_DURATION = Histogram(
                "http_server_request_duration_seconds",
                "HTTP request duration by method and normalized route.",
                ("method", "route"),
            )
            AUTHENTICATION_FAILED = Counter(
                "authentication_failed_total",
                "Failed bearer authentication decisions.",
            )
            AUTHORIZATION_DENIED = Counter(
                "authz_denied_total",
                "Default-deny authorization decisions.",
                ("resource", "action"),
            )
            DATABASE_DURATION = Histogram(
                "database_operation_duration_seconds",
                "Tenant-scoped database connection duration by outcome.",
                ("outcome",),
            )
            """
        ),
        f"src/{package_name}/security.py": _security_source(request),
        f"src/{package_name}/repository.py": clean(
            f"""
            from __future__ import annotations

            import os
            import stat
            import time
            from collections.abc import Iterator
            from contextlib import contextmanager
            from pathlib import Path
            from uuid import UUID

            import psycopg
            from psycopg import Connection
            from psycopg.rows import dict_row

            from .models import {", ".join(sorted(model_imports))}
            from .security import Identity
            from .telemetry import DATABASE_DURATION


            def _database_url() -> str:
                raw_path = os.getenv("ELMOS_DATABASE_URL_FILE", "")
                path = Path(raw_path)
                if not raw_path or not path.is_absolute() or path.is_symlink():
                    raise RuntimeError("ELMOS_DATABASE_URL_FILE_INVALID")
                details = path.stat()
                if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
                    raise RuntimeError("ELMOS_DATABASE_URL_FILE_UNSAFE")
                value = path.read_text(encoding="utf-8").strip()
                if not value.startswith(("postgresql://", "postgres://")) or len(value) > 4096:
                    raise RuntimeError("ELMOS_DATABASE_URL_FILE_INVALID")
                return value


            @contextmanager
            def tenant_connection(tenant_id: str) -> Iterator[Connection[dict[str, object]]]:
                started = time.perf_counter()
                outcome = "success"
                try:
                    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
                        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
                        yield connection
                except Exception:
                    outcome = "error"
                    raise
                finally:
                    DATABASE_DURATION.labels(outcome=outcome).observe(time.perf_counter() - started)


            def ready() -> bool:
                try:
                    with psycopg.connect(_database_url(), connect_timeout=2) as connection:
                        return connection.execute("SELECT 1").fetchone() == (1,)
                except (OSError, RuntimeError, psycopg.Error):
                    return False


            {repository_source}
            """
        ),
        f"src/{package_name}/app.py": clean(
            f"""
            from __future__ import annotations

            import json
            import logging
            import os
            import re
            import time
            from typing import Annotated
            from uuid import UUID, uuid4

            from fastapi import Depends, FastAPI, HTTPException, Request, Response
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
            from starlette.middleware.base import RequestResponseEndpoint
            from starlette.responses import Response as StarletteResponse

            from . import repository
            from .models import {", ".join(sorted(model_imports))}
            from .security import Identity, authorize
            from .telemetry import HTTP_DURATION, HTTP_REQUESTS

            app = FastAPI(title="{request.project_name}", version="1.0.0")
            logger = logging.getLogger("{package_name}")
            request_id_pattern = re.compile(r"^[A-Za-z0-9._:-]{{8,128}}$")


            @app.middleware("http")
            async def observe_request(
                request: Request,
                call_next: RequestResponseEndpoint,
            ) -> Response:
                supplied_id = request.headers.get("x-request-id", "")
                request_id = supplied_id if request_id_pattern.fullmatch(supplied_id) else str(uuid4())
                started = time.perf_counter()
                status_code = 500
                try:
                    response = await call_next(request)
                    status_code = response.status_code
                    response.headers["x-request-id"] = request_id
                    return response
                finally:
                    route = request.scope.get("route")
                    route_path = str(getattr(route, "path", "unmatched"))
                    HTTP_REQUESTS.labels(
                        method=request.method,
                        route=route_path,
                        status=str(status_code),
                    ).inc()
                    HTTP_DURATION.labels(method=request.method, route=route_path).observe(
                        time.perf_counter() - started
                    )
                    logger.info(
                        json.dumps(
                            {{
                                "timestamp": time.time(),
                                "level": "INFO",
                                "service": "{request.project_name}",
                                "request_id": request_id,
                                "route": route_path,
                                "status": status_code,
                            }},
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                    )


            @app.get("/health")
            @app.get("/health/live")
            def liveness() -> dict[str, str]:
                return {{"status": "UP", "service": os.getenv("APP_NAME", "{request.project_name}")}}


            @app.get("/health/ready")
            def readiness() -> dict[str, str]:
                if not repository.ready():
                    raise HTTPException(status_code=503, detail="database is unavailable")
                return {{"status": "UP", "service": os.getenv("APP_NAME", "{request.project_name}")}}


            @app.get("/metrics", include_in_schema=False)
            def metrics() -> StarletteResponse:
                return StarletteResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


            {route_source}
            """
        ),
        f"src/{package_name}/__main__.py": clean(
            f"""
            import os

            import uvicorn

            if __name__ == "__main__":
                uvicorn.run(
                    "{package_name}.app:app",
                    host=os.getenv("HOST", "127.0.0.1"),
                    port=int(os.getenv("PORT", "{port}")),
                    log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
                )
            """
        ),
        "scripts/local_runtime.py": _local_runtime_source(package_name, request.auth_mode),
        "scripts/create-test-identity.py": _test_identity_source(request.auth_mode),
        "tests/test_security.py": clean(
            f"""
            from fastapi.testclient import TestClient

            from {package_name}.app import app

            client = TestClient(app)


            def test_liveness_does_not_depend_on_database() -> None:
                response = client.get("/health/live")
                assert response.status_code == 200
                assert response.json()["status"] == "UP"


            def test_missing_bearer_token_is_denied() -> None:
                response = client.get("/api/v1/{request.entities[0].plural}")
                assert response.status_code == 401
            """
        ),
        "tests/test_postgresql_integration.py": clean(
            f"""
            import os
            import time
            from pathlib import Path

            import jwt
            import pytest
            from fastapi.testclient import TestClient

            from {package_name}.app import app

            pytestmark = pytest.mark.integration
            client = TestClient(app)


            def token(tenant_id: str) -> str:
                {integration_signing_setup}
                now = int(time.time())
                return jwt.encode(
                    {{
                        "iss": os.environ["ELMOS_AUTH_ISSUER"],
                        "aud": os.environ["ELMOS_AUTH_AUDIENCE"],
                        "sub": "integration-user",
                        "tenant_id": tenant_id,
                        "roles": {integration_roles},
                        "iat": now,
                        "exp": now + 300,
                    }},
                    signing_key,
                    algorithm=algorithm,
                    headers=headers,
                )


            {integration_test_source}
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {PYTHON_IMAGE} AS build
            WORKDIR /build
            COPY pyproject.toml ./
            COPY src ./src
            RUN python -m venv /opt/venv \
             && /opt/venv/bin/pip install --no-cache-dir .

            FROM {PYTHON_IMAGE}
            ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0
            RUN groupadd --system app && useradd --system --gid app --uid 10001 app
            COPY --from=build /opt/venv /opt/venv
            ENV PATH=/opt/venv/bin:$PATH
            WORKDIR /app
            USER 10001:10001
            EXPOSE {port}
            HEALTHCHECK --interval=10s --timeout=2s --retries=6 \\
              CMD ["python", "-c", {json.dumps(healthcheck)}]
            CMD ["python", "-m", "{package_name}"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="python", port=port),
        ".github/workflows/ci.yml": _ci_workflow(request.auth_mode),
        "Makefile": clean(
            f"""
            .PHONY: sync test integration check run migrate
            sync:
            \tuv lock
            \tuv sync --locked --python 3.12
            test:
            \tuv run pytest -m "not integration"
            integration:
            \tuv run python scripts/local_runtime.py --verify
            check:
            \tuv run ruff check src tests
            \tuv run mypy src
            migrate:
            \t../database/apply-migrations.sh
            run:
            \tPORT={port} uv run python scripts/local_runtime.py
            """
        ),
        "README.md": target_readme(
            request,
            language="Python 3.12",
            framework="FastAPI 0.116.1 + PostgreSQL 17.5",
            port=port,
            commands=(
                "uv lock\n"
                "uv sync --locked --python 3.12\n"
                "uv run pytest -m 'not integration'\n"
                "uv run python scripts/local_runtime.py --verify\n"
                f"PORT={port} uv run python scripts/local_runtime.py"
            ),
        ),
    }
