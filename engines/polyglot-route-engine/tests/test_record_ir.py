from __future__ import annotations

import pytest

from elmos_polyglot_route.models import (
    Expression,
    Function,
    Parameter,
    RecordDefinition,
    RouteError,
    SemanticIR,
    SourceSpan,
    Statement,
)
from elmos_polyglot_route.types import check, infer


def make_ir(
    functions: tuple[Function, ...],
    records: tuple[RecordDefinition, ...] = (),
    diagnostics: tuple[str, ...] = (),
) -> SemanticIR:
    return SemanticIR(
        source_language="python",
        source_file="test.py",
        analyzer="test-analyzer",
        analyzer_version="1.0.0",
        functions=functions,
        diagnostics=diagnostics,
        records=records,
    )


def test_record_definition_mapping_roundtrip() -> None:
    rec = RecordDefinition(
        name="Point",
        fields=(
            Parameter(name="x", type="integer"),
            Parameter(name="y", type="integer"),
        ),
        source_span=SourceSpan(file="test.py", start_byte=0, end_byte=10),
    )
    mapping = rec.to_mapping()
    assert mapping["name"] == "Point"
    assert len(mapping["fields"]) == 2
    assert mapping["fields"][0]["name"] == "x"
    assert mapping["fields"][0]["type"] == "integer"
    assert "source_span" in mapping

    rebuilt = RecordDefinition.from_mapping(mapping)
    assert rebuilt.name == "Point"
    assert len(rebuilt.fields) == 2
    assert rebuilt.fields[0].name == "x"
    assert rebuilt.fields[0].type == "integer"
    assert rebuilt.fields[1].name == "y"
    assert rebuilt.fields[1].type == "integer"
    assert rebuilt.source_span is not None
    assert rebuilt.source_span.file == "test.py"


def test_record_definition_rejections() -> None:
    # Invalid record name (empty or keywords or bad chars)
    with pytest.raises(RouteError):
        RecordDefinition.from_mapping({"name": "", "fields": [{"name": "x", "type": "integer"}]})

    with pytest.raises(RouteError):
        RecordDefinition.from_mapping({"name": "integer", "fields": [{"name": "x", "type": "integer"}]})

    with pytest.raises(RouteError):
        RecordDefinition.from_mapping({"name": "_Point", "fields": [{"name": "x", "type": "integer"}]})

    # Duplicate field
    with pytest.raises(RouteError, match="DUPLICATE_RECORD_FIELD"):
        RecordDefinition.from_mapping({
            "name": "Point",
            "fields": [
                {"name": "x", "type": "integer"},
                {"name": "x", "type": "integer"},
            ],
        })

    # Empty fields
    with pytest.raises(RouteError):
        RecordDefinition.from_mapping({"name": "Empty", "fields": []})


def test_member_access_and_record_construct_mapping() -> None:
    construct = Expression(
        kind="record_construct",
        record_name="Point",
        arguments=(
            ("x", Expression(kind="literal", value=10)),
            ("y", Expression(kind="literal", value=20)),
        ),
    )
    mapping = construct.to_mapping()
    assert mapping["kind"] == "record_construct"
    assert mapping["record_name"] == "Point"
    assert mapping["arguments"] == {
        "x": {"kind": "literal", "value": 10},
        "y": {"kind": "literal", "value": 20},
    }

    rebuilt_construct = Expression.from_mapping(mapping)
    assert rebuilt_construct.kind == "record_construct"
    assert rebuilt_construct.record_name == "Point"
    assert dict(rebuilt_construct.arguments)["x"].value == 10

    access = Expression(
        kind="member_access",
        target=construct,
        member="x",
    )
    access_mapping = access.to_mapping()
    assert access_mapping["kind"] == "member_access"
    assert access_mapping["member"] == "x"
    assert access_mapping["target"]["kind"] == "record_construct"

    rebuilt_access = Expression.from_mapping(access_mapping)
    assert rebuilt_access.kind == "member_access"
    assert rebuilt_access.member == "x"
    assert rebuilt_access.target is not None
    assert rebuilt_access.target.kind == "record_construct"


def test_semantic_ir_backward_compatibility() -> None:
    # When records is empty, to_mapping() and semantic_mapping() must not contain "records" key
    ir_no_records = make_ir(
        functions=(
            Function(
                name="f",
                parameters=(),
                return_type="integer",
                body=(Statement(kind="return", expression=Expression(kind="literal", value=42)),),
            ),
        ),
    )
    assert "records" not in ir_no_records.to_mapping()
    assert "records" not in ir_no_records.semantic_mapping()

    # When records is non-empty, to_mapping() contains "records"
    ir_with_records = make_ir(
        records=(
            RecordDefinition(
                name="Point",
                fields=(Parameter(name="x", type="integer"),),
            ),
        ),
        functions=(
            Function(
                name="f",
                parameters=(),
                return_type="integer",
                body=(Statement(kind="return", expression=Expression(kind="literal", value=42)),),
            ),
        ),
    )
    assert "records" in ir_with_records.to_mapping()
    assert len(ir_with_records.to_mapping()["records"]) == 1

    # Roundtrip from_mapping
    rebuilt = SemanticIR.from_mapping(ir_with_records.to_mapping())
    assert len(rebuilt.records) == 1
    assert rebuilt.records[0].name == "Point"


def test_record_type_checking_valid() -> None:
    point_rec = RecordDefinition(
        name="Point",
        fields=(
            Parameter(name="x", type="integer"),
            Parameter(name="y", type="integer"),
        ),
    )
    # fn get_x(p: Point) -> integer: return p.x
    fn_get_x = Function(
        name="get_x",
        parameters=(Parameter(name="p", type="Point"),),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="member_access",
                    target=Expression(kind="name", value="p"),
                    member="x",
                ),
            ),
        ),
    )
    # fn make_point(a: integer, b: integer) -> Point:
    #   let res: Point = Point(x=a, y=b)
    #   return res
    fn_make_point = Function(
        name="make_point",
        parameters=(
            Parameter(name="a", type="integer"),
            Parameter(name="b", type="integer"),
        ),
        return_type="Point",
        body=(
            Statement(
                kind="let",
                name="res",
                declared_type="Point",
                expression=Expression(
                    kind="record_construct",
                    record_name="Point",
                    arguments=(
                        ("x", Expression(kind="name", value="a")),
                        ("y", Expression(kind="name", value="b")),
                    ),
                ),
            ),
            Statement(
                kind="return",
                expression=Expression(kind="name", value="res"),
            ),
        ),
    )

    ir = make_ir(
        records=(point_rec,),
        functions=(fn_get_x, fn_make_point),
    )
    # Must pass type check
    check(ir)


def test_nested_record_type_checking() -> None:
    point_rec = RecordDefinition(
        name="Point",
        fields=(
            Parameter(name="x", type="integer"),
            Parameter(name="y", type="integer"),
        ),
    )
    line_rec = RecordDefinition(
        name="Line",
        fields=(
            Parameter(name="start", type="Point"),
            Parameter(name="end", type="Point"),
        ),
    )
    # fn get_start_x(line: Line) -> integer: return line.start.x
    fn = Function(
        name="get_start_x",
        parameters=(Parameter(name="line", type="Line"),),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="member_access",
                    target=Expression(
                        kind="member_access",
                        target=Expression(kind="name", value="line"),
                        member="start",
                    ),
                    member="x",
                ),
            ),
        ),
    )
    ir = make_ir(
        records=(point_rec, line_rec),
        functions=(fn,),
    )
    check(ir)


def test_record_type_checking_rejections() -> None:
    point_rec = RecordDefinition(
        name="Point",
        fields=(
            Parameter(name="x", type="integer"),
            Parameter(name="y", type="integer"),
        ),
    )

    # 1. Duplicate record name
    with pytest.raises(RouteError, match="DUPLICATE_RECORD_NAME"):
        check(make_ir(records=(point_rec, point_rec), functions=(
            Function(name="f", parameters=(), return_type="integer", body=(Statement(kind="return", expression=Expression(kind="literal", value=1)),)),
        )))

    # 2. Field of undefined record type
    bad_field_rec = RecordDefinition(
        name="Triangle",
        fields=(Parameter(name="a", type="NonExistentPoint"),),
    )
    with pytest.raises(RouteError, match="UNSUPPORTED_RECORD_FIELD_TYPE"):
        check(make_ir(records=(bad_field_rec,), functions=(
            Function(name="f", parameters=(), return_type="integer", body=(Statement(kind="return", expression=Expression(kind="literal", value=1)),)),
        )))

    # 3. Member access on scalar
    fn_bad_access = Function(
        name="bad",
        parameters=(Parameter(name="n", type="integer"),),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="member_access",
                    target=Expression(kind="name", value="n"),
                    member="x",
                ),
            ),
        ),
    )
    with pytest.raises(RouteError, match="MEMBER_ACCESS_ON_NON_RECORD"):
        check(make_ir(records=(point_rec,), functions=(fn_bad_access,)))

    # 4. Non-existent member access
    fn_unknown_member = Function(
        name="bad",
        parameters=(Parameter(name="p", type="Point"),),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="member_access",
                    target=Expression(kind="name", value="p"),
                    member="z",
                ),
            ),
        ),
    )
    with pytest.raises(RouteError, match="UNKNOWN_RECORD_MEMBER"):
        check(make_ir(records=(point_rec,), functions=(fn_unknown_member,)))

    # 5. Record construct with missing argument
    fn_missing_arg = Function(
        name="bad",
        parameters=(),
        return_type="Point",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="record_construct",
                    record_name="Point",
                    arguments=(("x", Expression(kind="literal", value=1)),),
                ),
            ),
        ),
    )
    with pytest.raises(RouteError, match="MISSING_RECORD_ARGUMENTS"):
        check(make_ir(records=(point_rec,), functions=(fn_missing_arg,)))

    # 6. Record construct with unexpected argument
    fn_extra_arg = Function(
        name="bad",
        parameters=(),
        return_type="Point",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="record_construct",
                    record_name="Point",
                    arguments=(
                        ("x", Expression(kind="literal", value=1)),
                        ("y", Expression(kind="literal", value=2)),
                        ("z", Expression(kind="literal", value=3)),
                    ),
                ),
            ),
        ),
    )
    with pytest.raises(RouteError, match="UNEXPECTED_RECORD_ARGUMENTS"):
        check(make_ir(records=(point_rec,), functions=(fn_extra_arg,)))

    # 7. Record construct argument type mismatch
    fn_wrong_type = Function(
        name="bad",
        parameters=(),
        return_type="Point",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="record_construct",
                    record_name="Point",
                    arguments=(
                        ("x", Expression(kind="literal", value="string_val")),
                        ("y", Expression(kind="literal", value=2)),
                    ),
                ),
            ),
        ),
    )
    with pytest.raises(RouteError, match="RECORD_ARGUMENT_TYPE_MISMATCH"):
        check(make_ir(records=(point_rec,), functions=(fn_wrong_type,)))

    # 8. Let statement type mismatch with record
    fn_let_mismatch = Function(
        name="bad",
        parameters=(),
        return_type="integer",
        body=(
            Statement(
                kind="let",
                name="p",
                declared_type="integer",
                expression=Expression(
                    kind="record_construct",
                    record_name="Point",
                    arguments=(
                        ("x", Expression(kind="literal", value=1)),
                        ("y", Expression(kind="literal", value=2)),
                    ),
                ),
            ),
            Statement(kind="return", expression=Expression(kind="name", value="p")),
        ),
    )
    with pytest.raises(RouteError, match="LET_TYPE_MISMATCH"):
        check(make_ir(records=(point_rec,), functions=(fn_let_mismatch,)))


def test_record_emission_all_14_targets() -> None:
    from elmos_polyglot_route.emitter import emit
    from elmos_polyglot_route.models import COMPLETE_MATRIX_LANGUAGES

    point_rec = RecordDefinition(
        name="Point",
        fields=(
            Parameter(name="x", type="integer"),
            Parameter(name="y", type="integer"),
        ),
    )
    # fn translate(p: Point, dx: integer, dy: integer) -> Point:
    #   return Point(x=p.x + dx, y=p.y + dy)
    fn_translate = Function(
        name="translate",
        parameters=(
            Parameter(name="p", type="Point"),
            Parameter(name="dx", type="integer"),
            Parameter(name="dy", type="integer"),
        ),
        return_type="Point",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="record_construct",
                    record_name="Point",
                    arguments=(
                        (
                            "x",
                            Expression(
                                kind="binary",
                                operator="+",
                                left=Expression(
                                    kind="member_access",
                                    target=Expression(kind="name", value="p"),
                                    member="x",
                                ),
                                right=Expression(kind="name", value="dx"),
                            ),
                        ),
                        (
                            "y",
                            Expression(
                                kind="binary",
                                operator="+",
                                left=Expression(
                                    kind="member_access",
                                    target=Expression(kind="name", value="p"),
                                    member="y",
                                ),
                                right=Expression(kind="name", value="dy"),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    ir = make_ir(records=(point_rec,), functions=(fn_translate,))

    targets = [
        "python",
        "java",
        "csharp",
        "typescript",
        "javascript",
        "go",
        "rust",
        "cpp",
        "objc",
        "swift",
        "kotlin",
        "flutter",
        "php",
        "react",
    ]

    for target in targets:
        emitted = emit(ir, target)
        content = emitted.content
        assert "Point" in content
        if target == "python":
            assert "@dataclass(frozen=True)" in content
            assert "class Point:" in content
            assert "x: int" in content
            assert ".x" in content
            assert "Point(x=" in content
        elif target == "java":
            assert "public record Point(long x, long y) {}" in content
            assert ".x()" in content
            assert "new Point(" in content
        elif target == "csharp":
            assert "public record Point(long x, long y);" in content
            assert ".x" in content
            assert "new Point(" in content
        elif target in {"typescript", "react"}:
            assert "export interface Point {" in content
            assert "readonly x: number;" in content
            assert ".x" in content
            assert "({ x:" in content
        elif target == "javascript":
            assert "@typedef {Object} Point" in content
            assert ".x" in content
            assert "({ x:" in content
        elif target == "go":
            assert "type Point struct {" in content
            assert "x int64" in content
            assert ".x" in content
            assert "Point{" in content
        elif target == "rust":
            assert "pub struct Point {" in content
            assert "pub x: i64," in content
            assert ".x" in content
            assert "Point {" in content
        elif target == "cpp":
            assert "struct Point {" in content
            assert "std::int64_t x;" in content
            assert ".x" in content
            assert "Point{" in content
        elif target == "objc":
            assert "typedef struct {" in content
            assert "long long x;" in content
            assert ".x" in content
            assert "(Point){" in content
        elif target == "swift":
            assert "struct Point: Equatable {" in content
            assert "let x: Int64" in content
            assert ".x" in content
            assert "Point(" in content
        elif target == "kotlin":
            assert "data class Point(" in content
            assert "val x: Long," in content
            assert ".x" in content
            assert "Point(" in content
        elif target == "flutter":
            assert "class Point {" in content
            assert "final int x;" in content
            assert ".x" in content
            assert "Point(" in content
        elif target == "php":
            assert "final readonly class Point {" in content
            assert "public int $x," in content
            assert "->x" in content
            assert "new Point(" in content


def test_python_analyzer_record_lifting(tmp_path: Path) -> None:
    from elmos_polyglot_route.python_analyzer import analyze_python

    py_file = tmp_path / "point_ops.py"
    py_file.write_text(
        "from dataclasses import dataclass\n\n"
        "@dataclass(frozen=True)\n"
        "class Point:\n"
        "    x: int\n"
        "    y: int\n\n"
        "def translate(p: Point, dx: int, dy: int) -> Point:\n"
        "    new_x: int = p.x + dx\n"
        "    new_y: int = p.y + dy\n"
        "    return Point(x=new_x, y=new_y)\n",
        encoding="utf-8",
    )

    ir = analyze_python(py_file, "translate")
    assert len(ir.records) == 1
    rec = ir.records[0]
    assert rec.name == "Point"
    assert len(rec.fields) == 2
    assert rec.fields[0].name == "x" and rec.fields[0].type == "integer"
    assert rec.fields[1].name == "y" and rec.fields[1].type == "integer"

    assert len(ir.functions) == 1
    fn = ir.functions[0]
    assert fn.name == "translate"
    assert fn.return_type == "Point"
    assert len(fn.parameters) == 3
    assert fn.parameters[0].name == "p" and fn.parameters[0].type == "Point"
    assert fn.parameters[1].name == "dx" and fn.parameters[1].type == "integer"
    assert fn.parameters[2].name == "dy" and fn.parameters[2].type == "integer"

    # Verify statements
    assert len(fn.body) == 3
    stmt0 = fn.body[0]
    assert stmt0.kind == "let" and stmt0.name == "new_x" and stmt0.declared_type == "integer"
    assert stmt0.expression.kind == "binary"
    assert stmt0.expression.left.kind == "member_access"
    assert stmt0.expression.left.target.value == "p" and stmt0.expression.left.member == "x"

    stmt2 = fn.body[2]
    assert stmt2.kind == "return"
    assert stmt2.expression.kind == "record_construct"
    assert stmt2.expression.record_name == "Point"
    assert len(stmt2.expression.arguments) == 2
    assert stmt2.expression.arguments[0][0] == "x" and stmt2.expression.arguments[0][1].value == "new_x"
    assert stmt2.expression.arguments[1][0] == "y" and stmt2.expression.arguments[1][1].value == "new_y"

    from elmos_polyglot_route.emitter import emit
    for target in ["python", "java", "csharp", "typescript", "javascript", "go", "rust", "cpp", "objc", "swift", "kotlin", "flutter", "php", "react"]:
        emitted = emit(ir, target)
        assert "Point" in emitted.content


def test_go_analyzer_record_lifting(tmp_path: Path) -> None:
    from elmos_polyglot_route.native import analyze
    from elmos_polyglot_route.emitter import emit

    go_file = tmp_path / "point.go"
    go_file.write_text(
        "package main\n\n"
        "type Point struct {\n"
        "    x int64\n"
        "    y int64\n"
        "}\n\n"
        "func translate(p Point, dx int64, dy int64) Point {\n"
        "    var new_x int64 = p.x + dx\n"
        "    var new_y int64 = p.y + dy\n"
        "    return Point{x: new_x, y: new_y}\n"
        "}\n",
        encoding="utf-8",
    )

    ir = analyze(go_file, "go", "translate")
    assert len(ir.records) == 1
    rec = ir.records[0]
    assert rec.name == "Point"
    assert len(rec.fields) == 2
    assert rec.fields[0].name == "x" and rec.fields[0].type == "integer"
    assert rec.fields[1].name == "y" and rec.fields[1].type == "integer"

    assert len(ir.functions) == 1
    fn = ir.functions[0]
    assert fn.name == "translate"
    assert fn.return_type == "Point"
    assert len(fn.parameters) == 3
    assert fn.parameters[0].name == "p" and fn.parameters[0].type == "Point"
    assert fn.parameters[1].name == "dx" and fn.parameters[1].type == "integer"
    assert fn.parameters[2].name == "dy" and fn.parameters[2].type == "integer"

    # Verify statements
    assert len(fn.body) == 3
    stmt0 = fn.body[0]
    assert stmt0.kind == "let" and stmt0.name == "new_x" and stmt0.declared_type == "integer"
    assert stmt0.expression.kind == "binary"
    assert stmt0.expression.left.kind == "member_access"
    assert stmt0.expression.left.target.value == "p" and stmt0.expression.left.member == "x"

    stmt2 = fn.body[2]
    assert stmt2.kind == "return"
    assert stmt2.expression.kind == "record_construct"
    assert stmt2.expression.record_name == "Point"
    assert len(stmt2.expression.arguments) == 2
    assert stmt2.expression.arguments[0][0] == "x" and stmt2.expression.arguments[0][1].value == "new_x"
    assert stmt2.expression.arguments[1][0] == "y" and stmt2.expression.arguments[1][1].value == "new_y"

    for target in ["python", "java", "csharp", "typescript", "javascript", "go", "rust", "cpp", "objc", "swift", "kotlin", "flutter", "php", "react"]:
        emitted = emit(ir, target)
        assert "Point" in emitted.content


def test_typescript_analyzer_record_lifting(tmp_path: Path) -> None:
    from elmos_polyglot_route.native import analyze
    from elmos_polyglot_route.emitter import emit

    ts_file = tmp_path / "point.ts"
    ts_file.write_text(
        "export interface Point {\n"
        "    readonly x: number;\n"
        "    readonly y: number;\n"
        "}\n\n"
        "export function translate(p: Point, dx: number, dy: number): Point {\n"
        "    const new_x: number = p.x + dx;\n"
        "    const new_y: number = p.y + dy;\n"
        "    return { x: new_x, y: new_y };\n"
        "}\n",
        encoding="utf-8",
    )

    ir = analyze(ts_file, "typescript", "translate")
    assert len(ir.records) == 1
    rec = ir.records[0]
    assert rec.name == "Point"
    assert len(rec.fields) == 2
    assert rec.fields[0].name == "x" and rec.fields[0].type == "number"
    assert rec.fields[1].name == "y" and rec.fields[1].type == "number"

    assert len(ir.functions) == 1
    fn = ir.functions[0]
    assert fn.name == "translate"
    assert fn.return_type == "Point"
    assert len(fn.parameters) == 3
    assert fn.parameters[0].name == "p" and fn.parameters[0].type == "Point"
    assert fn.parameters[1].name == "dx" and fn.parameters[1].type == "number"
    assert fn.parameters[2].name == "dy" and fn.parameters[2].type == "number"

    assert len(fn.body) == 3
    stmt0 = fn.body[0]
    assert stmt0.kind == "let" and stmt0.name == "new_x" and stmt0.declared_type == "number"
    assert stmt0.expression.kind == "binary"
    assert stmt0.expression.left.kind == "member_access"
    assert stmt0.expression.left.target.value == "p" and stmt0.expression.left.member == "x"

    stmt2 = fn.body[2]
    assert stmt2.kind == "return"
    assert stmt2.expression.kind == "record_construct"
    assert stmt2.expression.record_name == "Point"
    assert len(stmt2.expression.arguments) == 2
    assert stmt2.expression.arguments[0][0] == "x" and stmt2.expression.arguments[0][1].value == "new_x"
    assert stmt2.expression.arguments[1][0] == "y" and stmt2.expression.arguments[1][1].value == "new_y"

    for target in ["python", "java", "csharp", "typescript", "javascript", "go", "rust", "cpp", "objc", "swift", "kotlin", "flutter", "php", "react"]:
        emitted = emit(ir, target)
        assert "Point" in emitted.content


def test_typescript_type_alias_record_lifting(tmp_path: Path) -> None:
    from elmos_polyglot_route.native import analyze
    from elmos_polyglot_route.emitter import emit

    ts_file = tmp_path / "point_alias.ts"
    ts_file.write_text(
        "export type Point = {\n"
        "    x: number;\n"
        "    y: number;\n"
        "};\n\n"
        "export function get_x(p: Point): number {\n"
        "    return p.x;\n"
        "}\n",
        encoding="utf-8",
    )

    ir = analyze(ts_file, "typescript", "get_x")
    assert len(ir.records) == 1
    rec = ir.records[0]
    assert rec.name == "Point"
    assert len(rec.fields) == 2
    assert rec.fields[0].name == "x" and rec.fields[0].type == "number"
    assert rec.fields[1].name == "y" and rec.fields[1].type == "number"

    assert len(ir.functions) == 1
    fn = ir.functions[0]
    assert fn.name == "get_x"
    assert fn.return_type == "number"
    assert len(fn.body) == 1
    assert fn.body[0].kind == "return"
    assert fn.body[0].expression.kind == "member_access"
    assert fn.body[0].expression.target.value == "p"
    assert fn.body[0].expression.member == "x"



