"""Emit the shared local runtime harness used by every production target.

Provisioning a real PostgreSQL instance, applying the forward-only migration,
creating the least-privilege runtime role and minting local signing material is
identical work regardless of whether the application is Java, Go or PHP. Only
the launch command and the integration command differ.

Keeping one harness matters for evidence, not just for code size: if each
language provisioned its own database, a difference in role grants or in the
row-level-security setup would show up as a difference in test results that
looks like an application bug. Here every target is measured against the same
database, the same role and the same signing material.

The harness is emitted as a stdlib-only Python script. RSA material for the
OIDC mode is produced with ``openssl`` and the JWKS is derived from the modulus
it prints, so no target needs a Python cryptography dependency to be verified.
"""
from __future__ import annotations

from .production_contract import (
    DATABASE_NAME,
    DATABASE_ROLE,
    ENV_AUTH_AUDIENCE,
    ENV_AUTH_ISSUER,
    ENV_DATABASE_URL_FILE,
    ENV_JWT_SECRET_FILE,
    ENV_OIDC_JWKS_FILE,
    ENV_OIDC_PRIVATE_KEY_FILE,
    ENV_RUNTIME_STATE_DIR,
    LOCAL_AUDIENCE,
    LOCAL_ISSUER,
    LOCAL_KEY_ID,
)
from .rendering import clean

EXPECTED_POSTGRES_VERSIONS = (
    "postgres (PostgreSQL) 17.5",
    "postgres (PostgreSQL) 17.5 (Homebrew)",
)

# The emitted harness hardcodes these names inside its auth-material helpers.
# Generation is content addressed, so a silent divergence between the shared
# contract and the emitted script would change behaviour without changing any
# reviewed constant. Fail at import instead.
_EMITTED_AUTH_ENV_NAMES = {
    "jwt": (ENV_JWT_SECRET_FILE,),
    "oidc": (ENV_OIDC_JWKS_FILE, ENV_OIDC_PRIVATE_KEY_FILE),
}


#: Durability settings the generated runtime starts PostgreSQL with.
#:
#: ``certifying`` is the default and the only tier whose results may back a
#: production-equivalence claim: it keeps the same fsync and commit guarantees a
#: real deployment has. That is also what makes it the slowest part of a
#: verification run, and why it does not scale with concurrency -- every run on a
#: host competes for the same fsync queue, so latency grows faster than the
#: number of runs.
#:
#: ``fast-feedback`` trades those guarantees for turnaround during development.
#: A crash mid-run can leave the cluster unrecoverable and its results carry no
#: durability evidence whatsoever. It is opt-in and never inferred, and the tier
#: that produced a runtime is recorded beside it either way, so an artifact can
#: never be mistaken for a certifying one by looking at it.
#:
#: The tier is selected when the runtime is *started*, from the environment, not
#: when the workspace is generated. A generated workspace has to stay a function
#: of its approved request -- ``generate_workspace`` refuses to reuse an output
#: whose ``request_sha256`` moved, and the generation manifest digests every
#: file -- so a generation-time knob would let one request produce two different
#: workspaces and make the manifest ambiguous about which one it describes.
#: ``durability`` below only sets the default the emitted script falls back to.
DURABILITY_PROFILES: dict[str, tuple[str, ...]] = {
    "certifying": ("fsync=on", "synchronous_commit=on"),
    "fast-feedback": ("fsync=off", "synchronous_commit=off", "full_page_writes=off"),
}
DEFAULT_DURABILITY = "certifying"
#: Environment variable the emitted runtime reads to pick its durability tier.
ENV_POSTGRES_DURABILITY = "ELMOS_POSTGRES_DURABILITY"


def _command_literal(command: list[str]) -> str:
    return "[" + ", ".join(repr(part) for part in command) + "]"


def render_local_runtime(
    *,
    auth_mode: str,
    app_command: list[str],
    verify_command: list[str],
    migration_relative: str = "../database/migrations/001_initial.sql",
    app_port_argument_index: int | None = None,
    durability: str = DEFAULT_DURABILITY,
) -> str:
    """Render ``scripts/local_runtime.py`` for one language workspace.

    ``app_command`` and ``verify_command`` are argv lists executed from the
    language workspace root with the provisioned environment applied.
    """
    if auth_mode not in {"jwt", "oidc"}:
        raise ValueError(f"UNSUPPORTED_AUTH_MODE:{auth_mode}")
    if durability not in DURABILITY_PROFILES:
        raise ValueError(f"UNSUPPORTED_DURABILITY:{durability}")
    durability_table = "{" + ", ".join(
        f"{name!r}: {settings!r}" for name, settings in sorted(DURABILITY_PROFILES.items())
    ) + "}"
    if app_port_argument_index is not None:
        if (
            isinstance(app_port_argument_index, bool)
            or not 0 <= app_port_argument_index < len(app_command)
            or not app_command[app_port_argument_index].startswith("127.0.0.1:")
        ):
            raise ValueError("APP_PORT_ARGUMENT_INDEX_INVALID")

    auth_setup = _JWT_SETUP if auth_mode == "jwt" else _OIDC_SETUP
    for name in _EMITTED_AUTH_ENV_NAMES[auth_mode]:
        if f'"{name}"' not in auth_setup:
            raise ValueError(f"AUTH_ENV_NAME_DRIFT:{name}")
    if LOCAL_KEY_ID not in auth_setup and auth_mode == "oidc":
        raise ValueError(f"AUTH_KEY_ID_DRIFT:{LOCAL_KEY_ID}")
    # The emitted GRANT and role statements name only the fixed schema, database
    # and role identifiers declared in production_contract. No request text
    # reaches them, and every runtime value the script handles is a path it
    # created itself inside the workspace-confined state directory.
    return clean(
        f'''
        """Provision PostgreSQL and local signing material, then run the app.

        Generated by ELMOS. This script is the only component allowed to create
        local credentials, and it never writes them outside the workspace-confined
        runtime state directory.
        """
        from __future__ import annotations

        import atexit
        import base64
        import json
        import os
        import secrets
        import shutil
        import signal
        import subprocess
        import sys
        import tempfile
        import time
        from pathlib import Path

        EXPECTED_POSTGRES_VERSIONS = frozenset({tuple(sorted(EXPECTED_POSTGRES_VERSIONS))!r})
        APP_COMMAND = {_command_literal(app_command)}
        APP_PORT_ARGUMENT_INDEX = {app_port_argument_index!r}
        VERIFY_COMMAND = {_command_literal(verify_command)}
        MIGRATION_RELATIVE = {migration_relative!r}

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


        def resolved_app_command(environment: dict[str, str]) -> list[str]:
            command = list(APP_COMMAND)
            if APP_PORT_ARGUMENT_INDEX is None or "PORT" not in environment:
                return command
            try:
                port = int(environment["PORT"])
            except ValueError as error:
                raise RuntimeError("APP_PORT_INVALID") from error
            if not 1024 <= port <= 65535:
                raise RuntimeError("APP_PORT_INVALID")
            command[APP_PORT_ARGUMENT_INDEX] = f"127.0.0.1:{{port}}"
            return command


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


        def secure_state_directory() -> Path:
            workspace = Path.cwd().resolve()
            state = Path(os.getenv({ENV_RUNTIME_STATE_DIR!r}, ".elmos-runtime")).resolve()
            if state == workspace or workspace not in state.parents or state.is_symlink():
                raise RuntimeError("RUNTIME_STATE_DIRECTORY_MUST_BE_WORKSPACE_CONFINED")
            state.mkdir(parents=True, exist_ok=True, mode=0o700)
            return state


        def free_loopback_port() -> int:
            import socket as socket_module

            reserved: set[int] = set()
            app_port = os.environ.get("PORT")
            if app_port is not None:
                try:
                    reserved.add(int(app_port))
                except ValueError:
                    pass

            for _ in range(100):
                with socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM) as probe:
                    probe.bind(("127.0.0.1", 0))
                    candidate = int(probe.getsockname()[1])
                    if candidate not in reserved:
                        return candidate
            raise RuntimeError("FREE_LOOPBACK_PORT_EXHAUSTED")


        def start_postgres(state: Path) -> tuple[Path, Path, int]:
            """Start PostgreSQL on a loopback TCP port plus an admin socket.

            The Unix socket exists only for provisioning (trusted local admin);
            the application role connects over 127.0.0.1 with scram-sha-256, so
            the published URL works for every client stack including JDBC,
            which cannot dial libpq socket URLs.
            """
            global runtime_socket
            data = state / "postgres-data"
            temporary_root = Path(tempfile.gettempdir()).resolve()
            socket = Path(tempfile.mkdtemp(prefix="elmos-pg-", dir=temporary_root)).resolve()
            if socket.parent != temporary_root or not socket.name.startswith("elmos-pg-"):
                raise RuntimeError("POSTGRES_SOCKET_DIRECTORY_INVALID")
            socket.chmod(0o700)
            runtime_socket = socket

            postgres = required_tool("postgres")
            observed = subprocess.run(
                [str(postgres), "--version"], check=True, text=True, capture_output=True
            ).stdout.strip()
            if observed not in EXPECTED_POSTGRES_VERSIONS:
                raise RuntimeError(
                    "POSTGRES_VERSION_MISMATCH:"
                    f"expected={{sorted(EXPECTED_POSTGRES_VERSIONS)}}:observed={{observed}}"
                )
            binaries = postgres.parent
            if not data.exists():
                run([
                    str(binaries / "initdb"), "--pgdata", str(data),
                    "--auth-local=trust", "--auth-host=scram-sha-256",
                    "--encoding=UTF8", "--no-locale",
                ])
            port_file = state / "postgres-port"
            if port_file.exists():
                port = int(port_file.read_text(encoding="utf-8").strip())
            else:
                port = free_loopback_port()
                port_file.write_text(str(port), encoding="utf-8")
                port_file.chmod(0o600)
            # Selected here rather than baked in, so one generated workspace
            # stays one workspace. Unset means the certifying tier: relaxing
            # durability is something a run asks for, never something it drifts
            # into. Recorded next to the cluster it describes, because a runtime
            # directory that cannot say which tier produced it is a result
            # nobody can safely reuse as evidence.
            durability_profiles = {durability_table}
            durability = os.environ.get({ENV_POSTGRES_DURABILITY!r}, {durability!r})
            if durability not in durability_profiles:
                raise RuntimeError("UNSUPPORTED_POSTGRES_DURABILITY:" + durability)
            durability_file = state / "postgres-durability"
            durability_file.write_text(durability, encoding="utf-8")
            durability_file.chmod(0o600)
            database = subprocess.Popen([
                str(postgres), "-D", str(data), "-k", str(socket),
                "-h", "127.0.0.1", "-p", str(port),
                *[argument for setting in durability_profiles[durability] for argument in ("-c", setting)],
                "-c", "password_encryption=scram-sha-256",
            ])
            children.append(database)
            for _ in range(100):
                if database.poll() is not None:
                    raise RuntimeError("POSTGRES_START_FAILED")
                ready = subprocess.run(
                    [str(binaries / "pg_isready"), "-h", str(socket), "-p", str(port)],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("POSTGRES_START_TIMEOUT")
            return socket, binaries, port


        def provision_database(socket: Path, binaries: Path, state: Path, port: int) -> Path:
            def admin(database: str, sql: str) -> None:
                run([
                    str(binaries / "psql"), "-h", str(socket), "-p", str(port),
                    "-d", database, "-v", "ON_ERROR_STOP=1", "-c", sql,
                ])

            created = subprocess.run(
                [str(binaries / "createdb"), "-h", str(socket), "-p", str(port), {DATABASE_NAME!r}],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            if created.returncode != 0 and "already exists" not in created.stderr:
                raise RuntimeError("POSTGRES_DATABASE_CREATE_FAILED")
            admin(
                "postgres",
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {DATABASE_ROLE!r}) THEN "
                "CREATE ROLE {DATABASE_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
                "END IF; END $$;",
            )
            password_file = state / "postgres-password"
            if not password_file.exists():
                password_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
                password_file.chmod(0o600)
            if password_file.is_symlink() or password_file.stat().st_mode & 0o077:
                raise RuntimeError("LOCAL_DATABASE_PASSWORD_FILE_UNSAFE")
            password = password_file.read_text(encoding="utf-8").strip()
            # token_urlsafe stays inside [A-Za-z0-9_-], so the password needs no
            # URL escaping and cannot break the quoted SQL literal below.
            admin("postgres", "ALTER ROLE {DATABASE_ROLE} WITH PASSWORD '" + password + "';")
            migration = (Path.cwd() / MIGRATION_RELATIVE).resolve()
            if not migration.is_file():
                raise RuntimeError(f"MIGRATION_NOT_FOUND:{{migration}}")
            run([
                str(binaries / "psql"), "-h", str(socket), "-p", str(port),
                "-d", {DATABASE_NAME!r}, "-v", "ON_ERROR_STOP=1", "-f", str(migration),
            ])
            admin(
                {DATABASE_NAME!r},
                "GRANT USAGE ON SCHEMA app TO {DATABASE_ROLE}; "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO {DATABASE_ROLE}; "
                "ALTER DEFAULT PRIVILEGES IN SCHEMA app "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {DATABASE_ROLE};",
            )
            database_url_file = state / "database-url"
            # sslmode=disable: the server is loopback-only with scram passwords
            # and has no certificate; without the parameter lib/pq (which
            # defaults to sslmode=require) refuses the otherwise valid URL.
            database_url_file.write_text(
                "postgresql://{DATABASE_ROLE}:" + password
                + f"@127.0.0.1:{{port}}/{DATABASE_NAME}?sslmode=disable",
                encoding="utf-8",
            )
            database_url_file.chmod(0o600)
            return database_url_file


        def base64url(value: bytes) -> str:
            return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


{auth_setup}

        def main() -> int:
            atexit.register(stop_children)
            signal.signal(signal.SIGTERM, stop_children)
            signal.signal(signal.SIGINT, stop_children)
            state = secure_state_directory()
            socket, binaries, port = start_postgres(state)
            database_url_file = provision_database(socket, binaries, state, port)

            environment = dict(os.environ)
            # Database, application, and verifier are loopback-only. Ambient
            # proxies can turn direct local calls into 502 responses and must
            # not receive local auth or database traffic.
            for proxy_name in (
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy",
            ):
                environment.pop(proxy_name, None)
            environment["NO_PROXY"] = "127.0.0.1,localhost"
            environment["no_proxy"] = "127.0.0.1,localhost"
            environment[{ENV_DATABASE_URL_FILE!r}] = str(database_url_file)
            environment[{ENV_AUTH_ISSUER!r}] = {LOCAL_ISSUER!r}
            environment[{ENV_AUTH_AUDIENCE!r}] = {LOCAL_AUDIENCE!r}
            environment.update(provision_auth_material(state))

            if sys.argv[1:] == ["--verify"]:
                result = subprocess.run(VERIFY_COMMAND, check=False, env=environment)
                stop_children()
                return result.returncode
            if sys.argv[1:]:
                raise RuntimeError("LOCAL_RUNTIME_ARGUMENT_INVALID")
            app = subprocess.Popen(resolved_app_command(environment), env=environment)
            children.append(app)
            return_code = app.wait()
            stop_children()
            return return_code


        if __name__ == "__main__":
            raise SystemExit(main())
        '''
    )


_JWT_SETUP = """        def provision_auth_material(state: Path) -> dict[str, str]:
            secret_file = state / "jwt-hmac"
            if not secret_file.exists():
                secret_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
                secret_file.chmod(0o600)
            if secret_file.is_symlink() or secret_file.stat().st_mode & 0o077:
                raise RuntimeError("LOCAL_JWT_SECRET_FILE_UNSAFE")
            return {"ELMOS_JWT_HMAC_SECRET_FILE": str(secret_file)}
"""

_OIDC_SETUP = '''        def provision_auth_material(state: Path) -> dict[str, str]:
            """Mint an RSA keypair with openssl and derive its public JWKS.

            The modulus is read back from openssl rather than parsed out of the
            PEM so the harness needs no cryptography dependency; the exponent is
            fixed at 65537, which is what the generate call requests.
            """
            private_key_file = state / "oidc-private-key.pem"
            jwks_file = state / "oidc-jwks.json"
            if private_key_file.exists() != jwks_file.exists():
                raise RuntimeError("LOCAL_OIDC_KEYSET_INCOMPLETE")
            if not private_key_file.exists():
                openssl = shutil.which("openssl")
                if openssl is None:
                    raise RuntimeError("REQUIRED_TOOL_NOT_FOUND:openssl")
                subprocess.run(
                    [openssl, "genpkey", "-algorithm", "RSA",
                     "-pkeyopt", "rsa_keygen_bits:2048",
                     "-pkeyopt", "rsa_keygen_pubexp:65537",
                     "-out", str(private_key_file)],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                private_key_file.chmod(0o600)
                modulus_line = subprocess.run(
                    [openssl, "rsa", "-in", str(private_key_file), "-noout", "-modulus"],
                    check=True, text=True, capture_output=True,
                ).stdout.strip()
                if not modulus_line.startswith("Modulus="):
                    raise RuntimeError("LOCAL_OIDC_MODULUS_UNREADABLE")
                modulus = bytes.fromhex(modulus_line.removeprefix("Modulus="))
                jwks = {"keys": [{
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": "elmos-local-integration",
                    "n": base64url(modulus.lstrip(b"\\x00")),
                    "e": base64url((65537).to_bytes(3, "big")),
                }]}
                jwks_file.write_text(json.dumps(jwks, sort_keys=True), encoding="utf-8")
                jwks_file.chmod(0o600)
            if (
                private_key_file.is_symlink()
                or jwks_file.is_symlink()
                or private_key_file.stat().st_mode & 0o077
                or jwks_file.stat().st_mode & 0o077
            ):
                raise RuntimeError("LOCAL_OIDC_KEYSET_UNSAFE")
            return {
                "ELMOS_OIDC_JWKS_FILE": str(jwks_file),
                "ELMOS_OIDC_PRIVATE_KEY_FILE": str(private_key_file),
            }
'''
