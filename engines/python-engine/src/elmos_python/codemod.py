from __future__ import annotations

from dataclasses import dataclass

import libcst as cst


class OldPythonApiTransformer(cst.CSTTransformer):
    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        replacements = {"xrange": "range", "raw_input": "input"}
        return updated_node.with_changes(value=replacements.get(original_node.value, original_node.value))

    def leave_Attribute(self, original_node: cst.Attribute, updated_node: cst.Attribute) -> cst.Attribute:
        replacements = {"iteritems": "items", "iterkeys": "keys", "itervalues": "values"}
        if original_node.attr.value in replacements:
            return updated_node.with_changes(
                attr=updated_node.attr.with_changes(value=replacements[original_node.attr.value])
            )
        return updated_node


@dataclass(frozen=True)
class CodemodResult:
    transformed_source: str
    changed: bool
    comments_preserved: bool
    idempotent: bool
    attribution: tuple[str, ...]


class LibCstModernizer:
    def modernize_old_python_apis(self, source: str) -> CodemodResult:
        module = cst.parse_module(source)
        before_comments = tuple(line for line in source.splitlines() if line.strip().startswith("#"))
        transformed = module.visit(OldPythonApiTransformer()).code
        second = cst.parse_module(transformed).visit(OldPythonApiTransformer()).code
        after_comments = tuple(line for line in transformed.splitlines() if line.strip().startswith("#"))
        attribution = []
        for old, new in (
            ("xrange", "range"),
            ("raw_input", "input"),
            ("iteritems", "items"),
            ("iterkeys", "keys"),
            ("itervalues", "values"),
        ):
            if old in source and old not in transformed:
                attribution.append(f"{old}->{new}")
        return CodemodResult(
            transformed_source=transformed,
            changed=source != transformed,
            comments_preserved=before_comments == after_comments,
            idempotent=transformed == second,
            attribution=tuple(attribution),
        )
