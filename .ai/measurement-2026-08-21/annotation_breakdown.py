"""Why do candidates die at the type gate?

`PYTHON_PARAMETER_TYPE_REQUIRED` / `PYTHON_RETURN_TYPE_REQUIRED` collapse two
very different situations:

  MISSING_ANNOTATION   the author wrote no annotation at all
  UNSUPPORTED_TYPE     the author DID annotate, but with a type outside the
                       canonical four (int/float/bool/str)

The distinction decides whether "add type hints to the source" is a viable
remediation for repository conversion, or whether the canonical type surface
itself is the binding constraint.  This script re-walks the same corpus and
splits it, and also records which annotation spellings show up most.
"""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from pathlib import Path

from elmos_polyglot_route.project_graph import python_coverage_subjects

sys.path.insert(0, str(Path(__file__).parent))
from measure_admission import is_test_file, iter_python_files  # noqa: E402

CANONICAL = {"int", "float", "bool", "str"}


def annotation_text(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return "<unparseable>"


def main() -> int:
    corpus_root = Path(sys.argv[1]).resolve(strict=True)
    include_tests = "--include-tests" in sys.argv

    parameter_reason: Counter[str] = Counter()
    return_reason: Counter[str] = Counter()
    unsupported_parameter_spelling: Counter[str] = Counter()
    unsupported_return_spelling: Counter[str] = Counter()

    fully_canonical_signatures = 0
    checked = 0

    for repository in sorted(p for p in corpus_root.iterdir() if p.is_dir()):
        for path in iter_python_files(repository):
            relative = path.relative_to(repository).as_posix()
            if not include_tests and is_test_file(relative):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
            except Exception:
                continue
            # First definition wins, matching analyze_python's `next(...)` scan;
            # a dict comprehension would keep the LAST one and shift the count
            # by the number of duplicated top-level names.
            index: dict[str, ast.FunctionDef] = {}
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    index.setdefault(node.name, node)
            for subject in python_coverage_subjects(tree, relative):
                if not subject.candidate or subject.blocking_reasons:
                    continue
                node = index.get(subject.name)
                if node is None:
                    continue
                checked += 1

                signature_ok = True
                for argument in node.args.args:
                    text = annotation_text(argument.annotation)
                    if text is None:
                        parameter_reason["MISSING_ANNOTATION"] += 1
                        signature_ok = False
                    elif text not in CANONICAL:
                        parameter_reason["UNSUPPORTED_ANNOTATED_TYPE"] += 1
                        unsupported_parameter_spelling[text] += 1
                        signature_ok = False
                    else:
                        parameter_reason["CANONICAL"] += 1

                text = annotation_text(node.returns)
                if text is None:
                    return_reason["MISSING_ANNOTATION"] += 1
                    signature_ok = False
                elif text not in CANONICAL:
                    return_reason["UNSUPPORTED_ANNOTATED_TYPE"] += 1
                    unsupported_return_spelling[text] += 1
                    signature_ok = False
                else:
                    return_reason["CANONICAL"] += 1

                if signature_ok:
                    fully_canonical_signatures += 1

    report = {
        "kind": "elmos.python-type-gate-breakdown",
        "schema_version": "1.0.0",
        "corpus_root": str(corpus_root),
        "include_tests": include_tests,
        "candidates_examined": checked,
        "candidates_with_fully_canonical_signature": fully_canonical_signatures,
        "parameter_annotations": dict(parameter_reason.most_common()),
        "return_annotations": dict(return_reason.most_common()),
        "top_unsupported_parameter_annotations": dict(unsupported_parameter_spelling.most_common(25)),
        "top_unsupported_return_annotations": dict(unsupported_return_spelling.most_common(25)),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
