from __future__ import annotations
import argparse
import json
from pathlib import Path
from .cache import proof_cache_key
from .evidence import write_manifest, verify_manifest

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-formal")
    sub = parser.add_subparsers(dest="command", required=True)
    cache = sub.add_parser("cache-key")
    cache.add_argument("json_file", type=Path)
    bundle = sub.add_parser("bundle-manifest")
    bundle.add_argument("directory", type=Path)
    bundle.add_argument("--output", type=Path)
    verify = sub.add_parser("verify-bundle")
    verify.add_argument("directory", type=Path)
    verify.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    if args.command == "cache-key":
        print(proof_cache_key(json.loads(args.json_file.read_text(encoding="utf-8"))))
        return 0
    if args.command == "bundle-manifest":
        output = args.output or args.directory / "evidence-manifest.json"
        manifest = write_manifest(args.directory, output)
        print(manifest["manifestSha256"])
        return 0
    if args.command == "verify-bundle":
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        errors = verify_manifest(manifest, args.directory)
        if errors:
            print("\n".join(errors))
            return 1
        print("PASS")
        return 0
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
