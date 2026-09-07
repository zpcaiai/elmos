"""Execute one explicitly selected real qualification engineering probe."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from elmos_openhands.qualification_probes import (
    GoldenRepositorySpec,
    ProbeResult,
    run_browser_probe,
    run_chaos_probe,
    run_docker_sandbox_probe,
    run_golden_repository_probe,
    run_load_probe,
    run_postgres_probe,
    run_provider_probe,
    run_security_scan,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_qualification_probe")
    subparsers = parser.add_subparsers(dest="probe", required=True)
    postgres = subparsers.add_parser("postgres")
    postgres.add_argument("--dsn-env", default="OPENHANDS_POSTGRES_DSN")
    postgres.add_argument("--concurrency", type=int, default=8)
    postgres.add_argument("--events", type=int, default=64)
    provider = subparsers.add_parser("provider")
    provider.add_argument("--openai-token-env", default="OPENAI_API_KEY")
    provider.add_argument("--anthropic-token-env", default="ANTHROPIC_AUTH_TOKEN")
    provider.add_argument("--anthropic-base-url-env", default="ANTHROPIC_BASE_URL")
    provider.add_argument("--openai-model", default="gpt-5.4-mini-2026-03-17")
    provider.add_argument("--anthropic-model", default="claude-haiku-4-5-20251001")
    security = subparsers.add_parser("security")
    security.add_argument("--source-root", default="engines/openhands-absorption-engine/src/elmos_openhands")
    subparsers.add_parser("browser")
    load = subparsers.add_parser("load")
    load.add_argument("--dsn-env", default="OPENHANDS_POSTGRES_DSN")
    load.add_argument("--concurrency", type=int, default=16)
    load.add_argument("--events", type=int, default=256)
    sandbox = subparsers.add_parser("sandbox")
    sandbox.add_argument("--image-reference", required=True)
    chaos = subparsers.add_parser("chaos")
    chaos.add_argument("--dsn-env", default="OPENHANDS_POSTGRES_DSN")
    chaos.add_argument("--postgres-container", required=True)
    chaos.add_argument("--temporal-container", required=True)
    chaos.add_argument("--temporal-address", required=True)
    chaos.add_argument("--sandbox-image-reference", required=True)
    golden = subparsers.add_parser("golden")
    golden.add_argument("--clone-root", required=True)
    golden.add_argument(
        "--repository",
        action="append",
        default=[],
        metavar="ID=URL",
        help="repeat for at least three repositories",
    )
    args = parser.parse_args(argv)
    try:
        result = _execute(args)
    except Exception as error:  # noqa: BLE001 - CLI boundary converts failures to bounded evidence
        result = ProbeResult(
            str(args.probe),
            "FAIL",
            {},
            (type(error).__name__,),
            {"error": str(error)[:2000]},
        )
    print(json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":")))
    return 0 if result.status == "PASS" else 1


def _execute(args: argparse.Namespace) -> ProbeResult:
    if args.probe == "postgres":
        return run_postgres_probe(
            _required_environment(args.dsn_env),
            concurrency=args.concurrency,
            events=args.events,
        )
    if args.probe == "provider":
        return run_provider_probe(
            openai_token=_required_environment(args.openai_token_env),
            anthropic_token=_required_environment(args.anthropic_token_env),
            anthropic_base_url=_required_environment(args.anthropic_base_url_env),
            openai_model=args.openai_model,
            anthropic_model=args.anthropic_model,
        )
    if args.probe == "security":
        return run_security_scan(args.source_root)
    if args.probe == "browser":
        return run_browser_probe()
    if args.probe == "load":
        return run_load_probe(
            _required_environment(args.dsn_env),
            concurrency=args.concurrency,
            events=args.events,
        )
    if args.probe == "sandbox":
        return run_docker_sandbox_probe(args.image_reference)
    if args.probe == "chaos":
        return run_chaos_probe(
            _required_environment(args.dsn_env),
            postgres_container=args.postgres_container,
            temporal_container=args.temporal_container,
            temporal_address=args.temporal_address,
            sandbox_image_reference=args.sandbox_image_reference,
        )
    repositories = tuple(_repository(value) for value in args.repository)
    return run_golden_repository_probe(repositories, clone_root=Path(args.clone_root))


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("required environment variable is unavailable: " + name)
    return value


def _repository(value: str) -> GoldenRepositorySpec:
    repository_id, separator, url = value.partition("=")
    if not separator or not repository_id or not url.startswith("https://"):
        raise ValueError("repository must use ID=https://... syntax")
    return GoldenRepositorySpec(repository_id, url)


if __name__ == "__main__":
    sys.exit(main())
