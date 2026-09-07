#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return value


def case_ids(document: dict, field: str, path: Path) -> set[str]:
    entries = document.get(field)
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path}: {field} must be a non-empty array")
    identifiers: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: {field}[{index}] must be an object")
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"{path}: {field}[{index}].id is required")
        if identifier in identifiers:
            raise ValueError(f"{path}: duplicate case id {identifier}")
        identifiers.add(identifier)
    return identifiers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "pack_dir",
        nargs="?",
        default="client-packs/elmos-web-console-account-usage",
    )
    args = parser.parse_args()
    pack = Path(args.pack_dir).resolve()
    corpus = pack / "corpus"
    paths = {
        "development": corpus / "development" / "cases.json",
        "holdout": corpus / "holdout" / "cases.json",
        "representative": corpus / "representative-workloads" / "cases.json",
    }
    try:
        documents = {name: load(path) for name, path in paths.items()}
        identifiers = {
            "development": case_ids(documents["development"], "cases", paths["development"]),
            "holdout": case_ids(documents["holdout"], "cases", paths["holdout"]),
            "representative": case_ids(
                documents["representative"], "workloads", paths["representative"]
            ),
        }
        for left, right in (
            ("development", "holdout"),
            ("development", "representative"),
            ("holdout", "representative"),
        ):
            overlap = identifiers[left] & identifiers[right]
            if overlap:
                raise ValueError(f"corpora overlap between {left} and {right}: {sorted(overlap)}")

        development = documents["development"]
        holdout = documents["holdout"]
        representative = documents["representative"]
        if development.get("corpus") != "development" or development.get("may_author_rules") is not True:
            raise ValueError("development corpus ownership contract is invalid")
        if holdout.get("corpus") != "holdout":
            raise ValueError("holdout corpus identity is invalid")
        if holdout.get("independent_from_development") is not True or holdout.get("may_author_rules") is not False:
            raise ValueError("holdout corpus is not independently isolated")
        if holdout.get("external_verification_status") != "NOT_RUN":
            raise ValueError("local holdout must not claim external verification")
        if representative.get("customer_acceptance_status") != "NOT_RUN":
            raise ValueError("representative fixture must not claim customer acceptance")
        if any(document.get("contains_customer_data") is not False for document in documents.values()):
            raise ValueError("repository corpora must explicitly exclude customer data")

        certification = load(pack / "certification" / "certification.json")
        if certification.get("production_operation_authorized") is not False:
            raise ValueError("account-usage pack cannot authorize production operations")
        if certification.get("production_certification") != "NOT_CERTIFIED":
            raise ValueError("account-usage pack cannot self-certify")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "OK: account-usage corpora are non-overlapping; "
        "external verification, customer acceptance, and certification remain fail-closed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
