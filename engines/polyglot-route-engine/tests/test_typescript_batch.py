from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route import native
from elmos_polyglot_route.models import RouteError, SemanticIR


def test_real_typescript_batch_preserves_each_named_result_and_receipts(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "functions.ts"
    source.write_text(
        "export function add(a: number, b: number): number { return a + b; }\n"
        "export function subtract(a: number, b: number): number { return a - b; }\n"
    )
    calls = []
    original = native.typescript_parser_receipt
    def receipt():
        calls.append(1)
        return original()
    monkeypatch.setattr(native, "typescript_parser_receipt", receipt)
    names = ["add", "subtract", "missing"]
    batched = native.analyze_many(source, "typescript", names)
    # Two receipts still mean four complete closure captures: one safe private
    # parser/source snapshot serves all names, not a stale cross-request cache.
    assert len(calls) == 2
    for name in names:
        try:
            single = native.analyze(source, "typescript", name)
        except RouteError as error:
            assert isinstance(batched[name], RouteError)
            assert str(batched[name]) == str(error)
        else:
            assert isinstance(batched[name], SemanticIR)
            assert batched[name].to_mapping() == single.to_mapping()


@pytest.mark.parametrize("selector", ["--functions=a,a", "--functions=a,../x", "--functions=a,", "--functions=a"])
def test_batch_selector_rejects_invalid_names_before_toolchain(selector, tmp_path: Path) -> None:
    with pytest.raises(RouteError, match="COMMAND_SHAPE_INVALID"):
        native._run_trusted_typescript_analyzer(None, tmp_path / "not-used.ts", selector)
