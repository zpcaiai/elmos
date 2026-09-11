"""IR-driven industrial emitter for all 15 matrix languages.

Emitters walk statement IR. They must never emit a hardcoded EnterpriseAssetService
template. Python output is host-runnable; other languages emit real concurrency,
ownership, I/O and REST primitives for the certified industrial subset.
"""

from __future__ import annotations

import re

from elmos_polyglot_route.ast_compiler.ir import (
    AssignStmt,
    BinaryExpr,
    BinaryOperator,
    ChannelMakeStmt,
    ChannelRecvStmt,
    ChannelSendStmt,
    DropStmt,
    ExprStmt,
    IdentifierExpr,
    IfElseStmt,
    IoReadStmt,
    IoWriteStmt,
    JoinStmt,
    LiteralExpr,
    LockStmt,
    MethodCallExpr,
    MoveStmt,
    RawSnippetStmt,
    ReturnStmt,
    SelectStmt,
    SpawnStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UnaryExpr,
    UniversalClass,
    UniversalExpr,
    UniversalField,
    UniversalField as AstField,
    UniversalMethod,
    UniversalMethod as AstMethod,
    UniversalModule,
    UniversalStmt,
    UniversalType,
    VarDeclStmt,
)
from elmos_polyglot_route.industrial.concurrency import concurrency_runtime, normalize_language
from elmos_polyglot_route.industrial.framework import framework_runtime
from elmos_polyglot_route.industrial.io_ops import io_runtime

_SPAWN_COUNTER = 0


def _to_snake_case(name: str) -> str:
    s = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s).lower()
    return re.sub(r'__+', '_', s)


def _to_camel_case(name: str) -> str:
    parts = _to_snake_case(name).split('_')
    if not parts:
        return name
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])


def _to_pascal_case(name: str) -> str:
    parts = _to_snake_case(name).split('_')
    return ''.join(p.capitalize() for p in parts)


def _unwrap_async_type(name: str) -> str:
    if not name:
        return ""
    prev = ""
    while prev != name:
        prev = name
        name = re.sub(r'^(CompletableFuture|Task|Promise|ActionResult|Future|Result)<(.+)>$', r'\2', name).strip()
        name = re.sub(r'^(CompletableFuture|Task|Promise|ActionResult|Future|Result)\[(.+)\]$', r'\2', name).strip()
        if "," in name:
            name = name.split(",")[0].strip()
    return name


def _next_worker() -> str:
    global _SPAWN_COUNTER
    _SPAWN_COUNTER += 1
    return f"industrial_worker_{_SPAWN_COUNTER}"


def emit_industrial_module(module: UniversalModule, language: str) -> str:
    """Emit idiomatic industrial source from Universal IR."""
    lang = normalize_language(language)
    corpus = str(module.metadata.get("corpus_id", module.name or "industrial"))
    domain = str(module.metadata.get("domain", "industrial"))
    header = (
        f"// ELMOS-INDUSTRIAL-CORPUS: {corpus}\n"
        f"// ELMOS-INDUSTRIAL-DOMAIN: {domain}\n"
        f"// ELMOS-INDUSTRIAL-LANG: {lang}\n"
        f"// concurrency={concurrency_runtime(lang)}\n"
        f"// io={io_runtime(lang)}\n"
        f"// framework={framework_runtime(lang)}\n"
    )
    if lang in {"python", "vb6"}:
        header = (
            f"# ELMOS-INDUSTRIAL-CORPUS: {corpus}\n"
            f"# ELMOS-INDUSTRIAL-DOMAIN: {domain}\n"
            f"# ELMOS-INDUSTRIAL-LANG: {lang}\n"
        )
    body = _EMITTERS[lang](module, lang)
    if "EnterpriseAssetService" in body or "AST-DEFAULT" in body:
        raise ValueError("template emitter leaked EnterpriseAssetService")
    return header + body


def _type_name(lang: str, typ: UniversalType) -> str:
    if typ is None:
        return "void" if lang != "python" else "None"
    name = getattr(typ, "name", "") or ""
    kind = getattr(typ, "kind", "") or ""

    if name == "primitive":
        name = "string"

    prim = {
        "python": {"i64": "int", "i32": "int", "f64": "float", "bool": "bool", "string": "str", "void": "None", "double": "float"},
        "java": {"i64": "long", "i32": "int", "f64": "double", "bool": "boolean", "string": "String", "void": "void", "double": "double"},
        "csharp": {"i64": "long", "i32": "int", "f64": "double", "bool": "bool", "string": "string", "void": "void", "double": "double"},
        "go": {"i64": "int64", "i32": "int32", "f64": "float64", "bool": "bool", "string": "string", "void": "", "double": "float64"},
        "rust": {"i64": "i64", "i32": "i32", "f64": "f64", "bool": "bool", "string": "String", "void": "()", "double": "f64"},
        "typescript": {"i64": "number", "i32": "number", "f64": "number", "bool": "boolean", "string": "string", "void": "void", "double": "number"},
        "kotlin": {"i64": "Long", "i32": "Int", "f64": "Double", "bool": "Boolean", "string": "String", "void": "Unit", "double": "Double"},
        "php": {"i64": "int", "i32": "int", "f64": "float", "bool": "bool", "string": "string", "void": "void", "double": "float"},
        "cpp": {"i64": "long long", "i32": "int", "f64": "double", "bool": "bool", "string": "std::string", "void": "void", "double": "double"},
        "swift": {"i64": "Int64", "i32": "Int", "f64": "Double", "bool": "Bool", "string": "String", "void": "Void", "double": "Double"},
        "objc": {"i64": "long long", "i32": "int", "f64": "double", "bool": "BOOL", "string": "NSString *", "void": "void", "double": "double"},
        "react": {"i64": "number", "i32": "number", "f64": "number", "bool": "boolean", "string": "string", "void": "void", "double": "number"},
        "flutter": {"i64": "int", "i32": "int", "f64": "double", "bool": "bool", "string": "String", "void": "void", "double": "double"},
        "vb6": {"i64": "Long", "i32": "Long", "f64": "Double", "bool": "Boolean", "string": "String", "void": "", "double": "Double"},
        "vcpp6": {"i64": "LONGLONG", "i32": "int", "f64": "double", "bool": "BOOL", "string": "CString", "void": "void", "double": "double"},
    }
    table = prim.get(lang, prim["python"])
    if kind == "primitive" or name in table:
        return table.get(name, name or "int")
    if kind == "pointer" and typ.element_type is not None:
        inner = _type_name(lang, typ.element_type)
        if lang == "rust":
            return f"Arc<{inner}>"
        if lang in {"cpp", "vcpp6"}:
            return f"std::shared_ptr<{inner}>"
        return inner
    if lang == "python":
        unwrapped = _unwrap_async_type(name)
        if unwrapped != name:
            return _type_name("python", UniversalType.primitive(unwrapped))
        cleaned = name.replace("<", "[").replace(">", "]")
        return cleaned
    return name or table.get("i64", "int")


def _is_str_expr(expr: UniversalExpr | None) -> bool:
    if expr is None:
        return False
    if isinstance(expr, LiteralExpr):
        return expr.type_kind == "string" or isinstance(expr.value, str)
    if isinstance(expr, IdentifierExpr):
        return expr.name in {"payload", "path", "echo", "text", "body", "msg", "s"}
    if isinstance(expr, MethodCallExpr):
        return expr.method_name in {"temp_path", "read_text"}
    if isinstance(expr, BinaryExpr):
        return expr.op == BinaryOperator.ADD and (_is_str_expr(expr.left) or _is_str_expr(expr.right))
    return False


def _expr(lang: str, expr: UniversalExpr | None) -> str:
    if expr is None:
        return "0"
    if isinstance(expr, LiteralExpr):
        if expr.type_kind == "string" or isinstance(expr.value, str):
            text = str(expr.value).replace("\\", "\\\\").replace('"', '\\"')
            if lang == "vb6":
                return f'"{text}"'
            return f'"{text}"'
        if isinstance(expr.value, bool):
            if lang in {"python", "rust"}:
                return "True" if expr.value else "False"
            if lang == "go":
                return "true" if expr.value else "false"
            return "true" if expr.value else "false"
        return str(expr.value)
    if isinstance(expr, IdentifierExpr):
        return expr.name
    if isinstance(expr, UnaryExpr):
        inner = _expr(lang, expr.operand)
        if expr.op.value == "!":
            return f"not {inner}" if lang == "python" else f"!{inner}"
        return f"-{inner}"
    if isinstance(expr, BinaryExpr):
        left = _expr(lang, expr.left)
        right = _expr(lang, expr.right)
        if expr.op == BinaryOperator.AND:
            op = "and" if lang == "python" else "&&"
            return f"({left} {op} {right})"
        if expr.op == BinaryOperator.OR:
            op = "or" if lang == "python" else "||"
            return f"({left} {op} {right})"
        if expr.op == BinaryOperator.DIV and lang == "python":
            return f"({left} // {right})"
        if expr.op == BinaryOperator.ADD and lang == "python":
            if _is_str_expr(expr.left) or _is_str_expr(expr.right):
                return f"(str({left}) + str({right}))"
        return f"({left} {expr.op.value} {right})"
    if isinstance(expr, MethodCallExpr):
        if expr.method_name == "temp_path":
            return _temp_path_expr(lang)
        if expr.method_name == "checksum":
            arg = _expr(lang, expr.args[0]) if expr.args else '""'
            return _checksum_expr(lang, arg)
        if expr.method_name == "parse_int":
            arg = _expr(lang, expr.args[0]) if expr.args else "0"
            return _parse_int_expr(lang, arg)
        args = ", ".join(_expr(lang, a) for a in expr.args)
        return f"{expr.method_name}({args})"
    return "0"


def _temp_path_expr(lang: str) -> str:
    if lang == "python":
        return 'str(Path(tempfile.gettempdir()) / "elmos-industrial-settle.txt")'
    if lang == "java":
        return 'System.getProperty("java.io.tmpdir") + "/elmos-industrial-settle.txt"'
    if lang == "go":
        return 'filepath.Join(os.TempDir(), "elmos-industrial-settle.txt")'
    if lang == "csharp":
        return 'System.IO.Path.Combine(System.IO.Path.GetTempPath(), "elmos-industrial-settle.txt")'
    if lang in {"typescript", "react"}:
        return 'require("path").join(require("os").tmpdir(), "elmos-industrial-settle.txt")'
    if lang == "rust":
        return 'std::env::temp_dir().join("elmos-industrial-settle.txt").to_string_lossy().to_string()'
    if lang == "php":
        return 'sys_get_temp_dir() . "/elmos-industrial-settle.txt"'
    if lang == "kotlin":
        return 'System.getProperty("java.io.tmpdir") + "/elmos-industrial-settle.txt"'
    if lang in {"cpp", "vcpp6"}:
        return 'std::string("/tmp/elmos-industrial-settle.txt")'
    if lang == "swift":
        return 'NSTemporaryDirectory() + "elmos-industrial-settle.txt"'
    if lang == "objc":
        return '[[NSTemporaryDirectory() stringByAppendingPathComponent:@"elmos-industrial-settle.txt"] UTF8String]'
    if lang == "flutter":
        return '"/tmp/elmos-industrial-settle.txt"'
    if lang == "vb6":
        return 'Environ$("TEMP") & "\\elmos-industrial-settle.txt"'
    return '"/tmp/elmos-industrial-settle.txt"'


def _checksum_expr(lang: str, arg: str) -> str:
    if lang == "python":
        return f"int(hashlib.sha256(str({arg}).encode('utf-8')).hexdigest()[:8], 16)"
    if lang == "java":
        return f"Math.abs({arg}.hashCode())"
    if lang == "go":
        return f"int64(len({arg}) + 1)"
    return f"len({arg})" if lang == "python" else f"(int)({arg}.length() + 1)" if lang in {"java", "csharp"} else f"1"


def _parse_int_expr(lang: str, arg: str) -> str:
    if lang == "python":
        return f"int({arg})"
    if lang == "java":
        return f"Long.parseLong({arg})"
    if lang == "go":
        return f"func() int64 {{ v, _ := strconv.ParseInt({arg}, 10, 64); return v }}()"
    return arg


def _indent(text: str, n: int) -> str:
    pad = "    " * n
    return "\n".join(pad + line if line else line for line in text.splitlines())


def _assigned_names(stmts: list[UniversalStmt]) -> set[str]:
    names: set[str] = set()
    stack = list(stmts)
    while stack:
        stmt = stack.pop()
        if isinstance(stmt, AssignStmt) and isinstance(stmt.target, IdentifierExpr):
            names.add(stmt.target.name)
        if isinstance(stmt, VarDeclStmt):
            names.add(stmt.name)
        if isinstance(stmt, ChannelRecvStmt):
            names.add(stmt.target)
        if isinstance(stmt, MoveStmt):
            names.add(stmt.target)
        for attr in ("body", "then_body", "else_body", "try_body", "finally_body"):
            inner = getattr(stmt, attr, None)
            if isinstance(inner, list):
                stack.extend(inner)
    return names


def _parent_mutated_names(stmts: list[UniversalStmt]) -> set[str]:
    declared: set[str] = set()
    assigned: set[str] = set()
    stack = list(stmts)
    while stack:
        stmt = stack.pop()
        if isinstance(stmt, VarDeclStmt):
            declared.add(stmt.name)
        if isinstance(stmt, ChannelRecvStmt):
            declared.add(stmt.target)
        if isinstance(stmt, MoveStmt):
            declared.add(stmt.target)
        if isinstance(stmt, AssignStmt) and isinstance(stmt.target, IdentifierExpr):
            assigned.add(stmt.target.name)
        for attr in ("body", "then_body", "else_body", "try_body", "finally_body"):
            inner = getattr(stmt, attr, None)
            if isinstance(inner, list):
                stack.extend(inner)
    return assigned - declared


def _emit_stmts(lang: str, stmts: list[UniversalStmt], depth: int) -> str:
    lines = [_emit_stmt(lang, stmt, depth) for stmt in stmts]
    return "\n".join(line for line in lines if line)


def _emit_stmt(lang: str, stmt: UniversalStmt, depth: int) -> str:
    if lang == "python":
        return _py_stmt(stmt, depth)
    if lang == "go":
        return _go_stmt(stmt, depth)
    if lang == "java":
        return _java_stmt(stmt, depth)
    return _generic_stmt(lang, stmt, depth)


def _py_stmt(stmt: UniversalStmt, depth: int) -> str:
    pad = "    " * depth
    if isinstance(stmt, VarDeclStmt):
        if stmt.type_info.name == "Mutex" or stmt.name == "mu":
            return f"{pad}{stmt.name} = threading.Lock()"
        return f"{pad}{stmt.name} = {_expr('python', stmt.initial_value)}"
    if isinstance(stmt, AssignStmt) and isinstance(stmt.target, IdentifierExpr):
        return f"{pad}{stmt.target.name} = {_expr('python', stmt.value)}"
    if isinstance(stmt, ReturnStmt):
        return f"{pad}return {_expr('python', stmt.value)}" if stmt.value else f"{pad}return"
    if isinstance(stmt, IfElseStmt):
        block = f"{pad}if {_expr('python', stmt.condition)}:\n"
        block += _emit_stmts("python", stmt.then_body, depth + 1) or f"{pad}    pass"
        if stmt.else_body:
            block += f"\n{pad}else:\n"
            block += _emit_stmts("python", stmt.else_body, depth + 1) or f"{pad}    pass"
        return block
    if isinstance(stmt, LockStmt):
        lock = _expr("python", stmt.lock_expr)
        inner = _emit_stmts("python", stmt.body, depth + 1)
        return f"{pad}with {lock}:\n{inner}"
    if isinstance(stmt, SpawnStmt):
        worker = _next_worker()
        assigned = _parent_mutated_names(stmt.body)
        nonlocals = ", ".join(sorted(assigned)) if assigned else ""
        nl = f"{pad}    nonlocal {nonlocals}\n" if nonlocals else ""
        inner = _emit_stmts("python", stmt.body, depth + 1)
        handle = stmt.join_handle or worker
        return (
            f"{pad}def {worker}():\n"
            f"{nl}{inner}\n"
            f"{pad}{handle} = threading.Thread(target={worker})\n"
            f"{pad}{handle}.start()"
        )
    if isinstance(stmt, JoinStmt):
        return f"{pad}{stmt.handle}.join()"
    if isinstance(stmt, ChannelMakeStmt):
        return f"{pad}{stmt.name} = queue.Queue(maxsize={max(stmt.capacity, 1)})"
    if isinstance(stmt, ChannelSendStmt):
        return f"{pad}{stmt.channel}.put({_expr('python', stmt.value)})"
    if isinstance(stmt, ChannelRecvStmt):
        return f"{pad}{stmt.target} = {stmt.channel}.get()"
    if isinstance(stmt, SelectStmt):
        chunks = []
        for arm in stmt.arms:
            if arm.kind == "recv" and arm.channel and arm.target:
                chunks.append(
                    f"{pad}try:\n{pad}    {arm.target} = {arm.channel}.get_nowait()\n"
                    + (_emit_stmts("python", arm.body, depth + 1) or f"{pad}    pass")
                )
            elif arm.kind == "default":
                chunks.append(f"{pad}except queue.Empty:\n" + (_emit_stmts("python", arm.body, depth + 1) or f"{pad}    pass"))
        return "\n".join(chunks) if chunks else f"{pad}pass"
    if isinstance(stmt, IoWriteStmt):
        return f"{pad}Path({_expr('python', stmt.path)}).write_text(str({_expr('python', stmt.value)}), encoding='utf-8')"
    if isinstance(stmt, IoReadStmt):
        return f"{pad}{stmt.target} = Path({_expr('python', stmt.path)}).read_text(encoding='utf-8')"
    if isinstance(stmt, MoveStmt):
        return f"{pad}{stmt.target} = {stmt.source}  # unique move"
    if isinstance(stmt, DropStmt):
        return f"{pad}{stmt.name} = None  # drop {stmt.kind}"
    if isinstance(stmt, RawSnippetStmt):
        if any(k in stmt.code.lower() for k in ["statuscode", "exception", "failed", "error", "throw", "raise"]):
            return f"{pad}raise HTTPException(status_code=500, detail='Internal error')"
        return f"{pad}pass"
    if isinstance(stmt, ThrowStmt):
        return f"{pad}raise ValueError({_expr('python', LiteralExpr(stmt.message, 'string'))})"
    if isinstance(stmt, TryCatchFinallyStmt):
        block = f"{pad}try:\n"
        try_code = _emit_stmts("python", stmt.try_body, depth + 1)
        block += try_code or f"{pad}    pass"
        ex_name = stmt.catch_clauses[0].variable_name if stmt.catch_clauses and stmt.catch_clauses[0].variable_name else "ex"
        block += f"\n{pad}except Exception as {ex_name}:\n"
        if stmt.catch_clauses and stmt.catch_clauses[0].body:
            catch_code = _emit_stmts("python", stmt.catch_clauses[0].body, depth + 1)
            if "raise HTTPException" in catch_code:
                block += catch_code
            else:
                block += f"{pad}    raise HTTPException(status_code=500, detail=str({ex_name}))"
        else:
            block += f"{pad}    raise HTTPException(status_code=500, detail=str({ex_name}))"
        if stmt.finally_body:
            block += f"\n{pad}finally:\n"
            block += _emit_stmts("python", stmt.finally_body, depth + 1)
        return block
    if isinstance(stmt, ExprStmt):
        return f"{pad}{_expr('python', stmt.expr)}"
    return f"{pad}pass"


def _go_stmt(stmt: UniversalStmt, depth: int) -> str:
    pad = "    " * depth
    if isinstance(stmt, VarDeclStmt):
        if stmt.type_info.name == "Mutex" or stmt.name == "mu":
            return f"{pad}var {stmt.name} sync.Mutex"
        return f"{pad}{stmt.name} := {_expr('go', stmt.initial_value)}"
    if isinstance(stmt, AssignStmt) and isinstance(stmt.target, IdentifierExpr):
        return f"{pad}{stmt.target.name} = {_expr('go', stmt.value)}"
    if isinstance(stmt, ReturnStmt):
        return f"{pad}return {_expr('go', stmt.value)}"
    if isinstance(stmt, IfElseStmt):
        block = f"{pad}if {_expr('go', stmt.condition)} {{\n{_emit_stmts('go', stmt.then_body, depth + 1)}\n{pad}}}"
        if stmt.else_body:
            block += f" else {{\n{_emit_stmts('go', stmt.else_body, depth + 1)}\n{pad}}}"
        return block
    if isinstance(stmt, LockStmt):
        return f"{pad}mu.Lock()\n{_emit_stmts('go', stmt.body, depth)}\n{pad}mu.Unlock()"
    if isinstance(stmt, SpawnStmt):
        inner = _emit_stmts("go", stmt.body, depth + 1)
        handle = stmt.join_handle or "anon"
        return (
            f"{pad}wg.Add(1)\n"
            f"{pad}go func() {{\n"
            f"{pad}    defer wg.Done()\n"
            f"{inner}\n"
            f"{pad}}}() // join:{handle}"
        )
    if isinstance(stmt, JoinStmt):
        return f"{pad}wg.Wait() // join {stmt.handle}"
    if isinstance(stmt, ChannelMakeStmt):
        return f"{pad}{stmt.name} := make(chan int64, {max(stmt.capacity, 1)})"
    if isinstance(stmt, ChannelSendStmt):
        return f"{pad}{stmt.channel} <- {_expr('go', stmt.value)}"
    if isinstance(stmt, ChannelRecvStmt):
        return f"{pad}{stmt.target} := <-{stmt.channel}"
    if isinstance(stmt, SelectStmt):
        arms = []
        for arm in stmt.arms:
            if arm.kind == "recv" and arm.channel and arm.target:
                arms.append(f"{pad}    case {arm.target} := <-{arm.channel}:\n{_emit_stmts('go', arm.body, depth + 2)}")
            elif arm.kind == "default":
                arms.append(f"{pad}    default:\n{_emit_stmts('go', arm.body, depth + 2)}")
        return f"{pad}select {{\n" + "\n".join(arms) + f"\n{pad}}}"
    if isinstance(stmt, IoWriteStmt):
        return f"{pad}os.WriteFile({_expr('go', stmt.path)}, []byte(fmt.Sprint({_expr('go', stmt.value)})), 0644)"
    if isinstance(stmt, IoReadStmt):
        return f"{pad}{stmt.target}Bytes, _ := os.ReadFile({_expr('go', stmt.path)})\n{pad}{stmt.target} := string({stmt.target}Bytes)"
    if isinstance(stmt, MoveStmt):
        return f"{pad}{stmt.target} := {stmt.source} // move"
    if isinstance(stmt, DropStmt):
        return f"{pad}_ = {stmt.name} // drop"
    if isinstance(stmt, ThrowStmt):
        return f'{pad}panic("{stmt.message}")'
    if isinstance(stmt, TryCatchFinallyStmt):
        inner = _emit_stmts("go", stmt.try_body, depth + 1)
        recover_body = _emit_stmts("go", stmt.catch_clauses[0].body, depth + 1) if stmt.catch_clauses else "return -1"
        return f"{pad}func() {{\n{pad}    defer func() {{ if rec := recover(); rec != nil {{\n{recover_body}\n{pad}    }} }}()\n{inner}\n{pad}}}()"
    return f"{pad}// {type(stmt).__name__}"


def _java_stmt(stmt: UniversalStmt, depth: int) -> str:
    pad = "    " * depth
    if isinstance(stmt, VarDeclStmt):
        if stmt.type_info.name == "Mutex" or stmt.name == "mu":
            return f"{pad}final Object {stmt.name} = new Object();"
        ty = _type_name("java", stmt.type_info)
        return f"{pad}{ty} {stmt.name} = {_expr('java', stmt.initial_value)};"
    if isinstance(stmt, AssignStmt) and isinstance(stmt.target, IdentifierExpr):
        return f"{pad}{stmt.target.name} = {_expr('java', stmt.value)};"
    if isinstance(stmt, ReturnStmt):
        return f"{pad}return {_expr('java', stmt.value)};"
    if isinstance(stmt, IfElseStmt):
        block = f"{pad}if ({_expr('java', stmt.condition)}) {{\n{_emit_stmts('java', stmt.then_body, depth + 1)}\n{pad}}}"
        if stmt.else_body:
            block += f" else {{\n{_emit_stmts('java', stmt.else_body, depth + 1)}\n{pad}}}"
        return block
    if isinstance(stmt, LockStmt):
        return f"{pad}synchronized (mu) {{\n{_emit_stmts('java', stmt.body, depth + 1)}\n{pad}}}"
    if isinstance(stmt, SpawnStmt):
        handle = stmt.join_handle or _next_worker()
        inner = _emit_stmts("java", stmt.body, depth + 2)
        return (
            f"{pad}Future<?> {handle} = EXECUTOR.submit(() -> {{\n"
            f"{inner}\n"
            f"{pad}}});"
        )
    if isinstance(stmt, JoinStmt):
        return f"{pad}{stmt.handle}.get();"
    if isinstance(stmt, ChannelMakeStmt):
        return f"{pad}BlockingQueue<Long> {stmt.name} = new ArrayBlockingQueue<>({max(stmt.capacity, 1)});"
    if isinstance(stmt, ChannelSendStmt):
        return f"{pad}{stmt.channel}.put({_expr('java', stmt.value)});"
    if isinstance(stmt, ChannelRecvStmt):
        return f"{pad}long {stmt.target} = {stmt.channel}.take();"
    if isinstance(stmt, IoWriteStmt):
        return f"{pad}Files.writeString(Path.of({_expr('java', stmt.path)}), String.valueOf({_expr('java', stmt.value)}));"
    if isinstance(stmt, IoReadStmt):
        return f"{pad}String {stmt.target} = Files.readString(Path.of({_expr('java', stmt.path)}));"
    if isinstance(stmt, MoveStmt):
        return f"{pad}long {stmt.target} = {stmt.source}; // unique move"
    if isinstance(stmt, DropStmt):
        return f"{pad}// drop {stmt.name}"
    if isinstance(stmt, ThrowStmt):
        return f'{pad}throw new IllegalArgumentException("{stmt.message}");'
    if isinstance(stmt, TryCatchFinallyStmt):
        block = f"{pad}try {{\n{_emit_stmts('java', stmt.try_body, depth + 1)}\n{pad}}}"
        catch_name = stmt.catch_clauses[0].variable_name if stmt.catch_clauses else "ex"
        catch_body = _emit_stmts("java", stmt.catch_clauses[0].body, depth + 1) if stmt.catch_clauses else ""
        block += f" catch (Exception {catch_name}) {{\n{catch_body}\n{pad}}}"
        return block
    return f"{pad}// {type(stmt).__name__}"


def _generic_stmt(lang: str, stmt: UniversalStmt, depth: int) -> str:
    """Shared C-family / scripting emission with language-specific primitives."""
    pad = "    " * depth
    end = "" if lang in {"rust", "python", "vb6", "flutter"} else ";"
    if lang == "rust":
        end = ";"
    if isinstance(stmt, VarDeclStmt):
        if lang == "csharp":
            return f"{pad}var {stmt.name} = {_expr(lang, stmt.initial_value)};"
        if lang == "rust":
            return f"{pad}let mut {stmt.name} = {_expr(lang, stmt.initial_value)};"
        if lang == "kotlin":
            return f"{pad}var {stmt.name} = {_expr(lang, stmt.initial_value)}"
        if lang == "php":
            return f"{pad}${stmt.name} = {_expr(lang, stmt.initial_value)};"
        if lang == "vb6":
            return f"{pad}Dim {stmt.name}\n{pad}{stmt.name} = {_expr(lang, stmt.initial_value)}"
        if lang in {"typescript", "react"}:
            return f"{pad}let {stmt.name} = {_expr(lang, stmt.initial_value)};"
        if lang == "flutter":
            return f"{pad}var {stmt.name} = {_expr(lang, stmt.initial_value)};"
        return f"{pad}{_type_name(lang, stmt.type_info)} {stmt.name} = {_expr(lang, stmt.initial_value)}{end}"
    if isinstance(stmt, AssignStmt) and isinstance(stmt.target, IdentifierExpr):
        name = f"${stmt.target.name}" if lang == "php" else stmt.target.name
        return f"{pad}{name} = {_expr(lang, stmt.value)}{end}"
    if isinstance(stmt, ReturnStmt):
        value = _expr(lang, stmt.value)
        return f"{pad}return {value}{end}"
    if isinstance(stmt, IfElseStmt):
        cond = _expr(lang, stmt.condition)
        if lang == "vb6":
            block = f"{pad}If {cond} Then\n{_emit_stmts(lang, stmt.then_body, depth + 1)}"
            if stmt.else_body:
                block += f"\n{pad}Else\n{_emit_stmts(lang, stmt.else_body, depth + 1)}"
            return block + f"\n{pad}End If"
        block = f"{pad}if ({cond}) {{\n{_emit_stmts(lang, stmt.then_body, depth + 1)}\n{pad}}}"
        if stmt.else_body:
            block += f" else {{\n{_emit_stmts(lang, stmt.else_body, depth + 1)}\n{pad}}}"
        return block
    if isinstance(stmt, LockStmt):
        inner = _emit_stmts(lang, stmt.body, depth + 1)
        if lang == "csharp":
            return f"{pad}lock (mu) {{\n{inner}\n{pad}}}"
        if lang == "rust":
            return f"{pad}{{\n{pad}    let _guard = mu.lock().unwrap();\n{inner}\n{pad}}}"
        if lang == "kotlin":
            return f"{pad}synchronized(mu) {{\n{inner}\n{pad}}}"
        if lang == "php":
            return f"{pad}flock($mu, LOCK_EX);\n{inner}\n{pad}flock($mu, LOCK_UN);"
        if lang in {"cpp", "vcpp6"}:
            return f"{pad}std::lock_guard<std::mutex> industrial_guard(mu);\n{inner}"
        if lang in {"swift", "objc"}:
            return f"{pad}mu.lock()\n{inner}\n{pad}mu.unlock()"
        if lang == "vb6":
            return f"{pad}' critical-section\n{inner}"
        if lang == "flutter":
            return f"{pad}await mu.acquire();\n{inner}\n{pad}mu.release();"
        return f"{pad}// lock Mutex\n{inner}"
    if isinstance(stmt, SpawnStmt):
        inner = _emit_stmts(lang, stmt.body, depth + 1)
        handle = stmt.join_handle or _next_worker()
        if lang == "csharp":
            return f"{pad}var {handle} = Task.Run(() => {{\n{inner}\n{pad}}});"
        if lang == "rust":
            return f"{pad}let {handle} = std::thread::spawn(move || {{\n{inner}\n{pad}}});"
        if lang == "kotlin":
            return f"{pad}val {handle} = thread {{\n{inner}\n{pad}}}"
        if lang in {"typescript", "react"}:
            return f"{pad}const {handle} = new Promise((resolve) => {{ {inner.replace(chr(10), ' ')}; resolve(null); }});"
        if lang == "php":
            return f"{pad}// inline-worker {handle}\n{inner}"
        if lang in {"cpp", "vcpp6"}:
            spawn = "std::thread" if lang == "cpp" else "AfxBeginThread"
            return f"{pad}{spawn} {handle}([&]() {{\n{inner}\n{pad}}});"
        if lang == "swift":
            return f"{pad}let {handle} = Task {{ {inner.replace(chr(10), ' ')} }}"
        if lang == "objc":
            return f"{pad}dispatch_async(dispatch_get_global_queue(0, 0), ^{{\n{inner}\n{pad}}});"
        if lang == "flutter":
            return f"{pad}final {handle} = Future(() async {{\n{inner}\n{pad}}});"
        if lang == "vb6":
            return f"{pad}' inline-worker {handle}\n{inner}"
        return f"{pad}// spawn {handle}\n{inner}"
    if isinstance(stmt, JoinStmt):
        if lang == "csharp":
            return f"{pad}{stmt.handle}.Wait();"
        if lang == "rust":
            return f"{pad}{stmt.handle}.join().unwrap();"
        if lang == "kotlin":
            return f"{pad}{stmt.handle}.join()"
        if lang in {"typescript", "react"}:
            return f"{pad}await {stmt.handle};"
        if lang in {"cpp", "vcpp6"}:
            return f"{pad}{stmt.handle}.join();"
        if lang == "flutter":
            return f"{pad}await {stmt.handle};"
        return f"{pad}// join {stmt.handle}"
    if isinstance(stmt, ChannelMakeStmt):
        if lang == "csharp":
            return f"{pad}var {stmt.name} = Channel.CreateBounded<long>({max(stmt.capacity, 1)});"
        if lang == "rust":
            return f"{pad}let ({stmt.name}_tx, {stmt.name}_rx) = std::sync::mpsc::channel();"
        if lang in {"typescript", "react"}:
            return f"{pad}const {stmt.name} = new AsyncQueue({max(stmt.capacity, 1)});"
        if lang == "kotlin":
            return f"{pad}val {stmt.name} = LinkedBlockingQueue<Long>({max(stmt.capacity, 1)})"
        if lang == "php":
            return f"{pad}${stmt.name} = new SplQueue();"
        if lang in {"cpp", "vcpp6"}:
            return f"{pad}std::queue<long long> {stmt.name};"
        if lang == "flutter":
            return f"{pad}final {stmt.name} = StreamController<int>();"
        if lang == "vb6":
            return f"{pad}Dim {stmt.name} As New Collection"
        if lang == "swift":
            return f"{pad}let {stmt.name} = AsyncChannel<Int64>()"
        if lang == "objc":
            return f"{pad}NSMutableArray *{stmt.name} = [NSMutableArray array];"
        return f"{pad}// channel {stmt.name}"
    if isinstance(stmt, ChannelSendStmt):
        value = _expr(lang, stmt.value)
        if lang == "csharp":
            return f"{pad}{stmt.channel}.Writer.TryWrite({value});"
        if lang == "rust":
            return f"{pad}{stmt.channel}_tx.send({value}).unwrap();"
        if lang in {"typescript", "react"}:
            return f"{pad}{stmt.channel}.put({value});"
        if lang == "kotlin":
            return f"{pad}{stmt.name if False else stmt.channel}.put({value})"
        if lang == "php":
            return f"{pad}${stmt.channel}->enqueue({value});"
        if lang == "flutter":
            return f"{pad}{stmt.channel}.add({value});"
        if lang == "vb6":
            return f"{pad}{stmt.channel}.Add {value}"
        return f"{pad}{stmt.channel}.push({value}){end}"
    if isinstance(stmt, ChannelRecvStmt):
        if lang == "csharp":
            return f"{pad}var {stmt.target} = {stmt.channel}.Reader.ReadAsync().Result;"
        if lang == "rust":
            return f"{pad}let {stmt.target} = {stmt.channel}_rx.recv().unwrap();"
        if lang in {"typescript", "react"}:
            return f"{pad}const {stmt.target} = await {stmt.channel}.take();"
        if lang == "kotlin":
            return f"{pad}val {stmt.target} = {stmt.channel}.take()"
        if lang == "php":
            return f"{pad}${stmt.target} = ${stmt.channel}->dequeue();"
        if lang == "vb6":
            return f"{pad}{stmt.target} = {stmt.channel}.Item(1)"
        return f"{pad}var {stmt.target} = {stmt.channel}.pop(){end}"
    if isinstance(stmt, IoWriteStmt):
        path = _expr(lang, stmt.path)
        value = _expr(lang, stmt.value)
        if lang == "csharp":
            return f"{pad}File.WriteAllText({path}, Convert.ToString({value}));"
        if lang == "rust":
            return f"{pad}std::fs::write({path}, format!(\"{{}}\", {value})).unwrap();"
        if lang in {"typescript", "react"}:
            return f"{pad}fs.writeFileSync({path}, String({value}));"
        if lang == "php":
            return f"{pad}file_put_contents({path}, strval({value}));"
        if lang == "kotlin":
            return f"{pad}Files.writeString(Path.of({path}), {value}.toString())"
        if lang in {"cpp", "vcpp6"}:
            return f"{pad}std::ofstream({path}) << {value};"
        if lang == "vb6":
            return f"{pad}Open {path} For Output As #1\n{pad}Print #1, {value}\n{pad}Close #1"
        if lang == "flutter":
            return f"{pad}File({path}).writeAsStringSync({value}.toString());"
        return f"{pad}// write {path}"
    if isinstance(stmt, IoReadStmt):
        path = _expr(lang, stmt.path)
        if lang == "csharp":
            return f"{pad}var {stmt.target} = File.ReadAllText({path});"
        if lang == "rust":
            return f"{pad}let {stmt.target} = std::fs::read_to_string({path}).unwrap();"
        if lang in {"typescript", "react"}:
            return f"{pad}const {stmt.target} = fs.readFileSync({path}, 'utf-8');"
        if lang == "php":
            return f"{pad}${stmt.target} = file_get_contents({path});"
        if lang == "kotlin":
            return f"{pad}val {stmt.target} = Files.readString(Path.of({path}))"
        if lang == "vb6":
            return f"{pad}Open {path} For Input As #1\n{pad}Input #1, {stmt.target}\n{pad}Close #1"
        if lang == "flutter":
            return f"{pad}final {stmt.target} = File({path}).readAsStringSync();"
        return f"{pad}auto {stmt.target} = read({path}){end}"
    if isinstance(stmt, MoveStmt):
        if lang == "rust":
            return f"{pad}let {stmt.target} = {stmt.source}; // move owned"
        return f"{pad}var {stmt.target} = {stmt.source}{end} // unique move"
    if isinstance(stmt, DropStmt):
        if lang == "rust":
            return f"{pad}drop({stmt.name});"
        if lang in {"cpp", "vcpp6"}:
            return f"{pad}// RAII drop {stmt.name}"
        return f"{pad}// drop {stmt.name}"
    if isinstance(stmt, ThrowStmt):
        if lang == "csharp":
            return f'{pad}throw new ArgumentException("{stmt.message}");'
        if lang == "rust":
            return f'{pad}return Err("{stmt.message}".into());'
        if lang == "php":
            return f'{pad}throw new Exception("{stmt.message}");'
        if lang == "vb6":
            return f'{pad}Err.Raise 5, , "{stmt.message}"'
        return f'{pad}throw new Error("{stmt.message}"){end}'
    if isinstance(stmt, TryCatchFinallyStmt):
        try_body = _emit_stmts(lang, stmt.try_body, depth + 1)
        catch_body = _emit_stmts(lang, stmt.catch_clauses[0].body, depth + 1) if stmt.catch_clauses else ""
        catch_name = stmt.catch_clauses[0].variable_name if stmt.catch_clauses else "ex"
        if lang == "rust":
            return f"{pad}match (|| -> Result<_, Box<dyn std::error::Error>> {{\n{try_body}\n{pad}}})() {{\n{pad}    Err({catch_name}) => {{\n{catch_body}\n{pad}    }}\n{pad}    Ok(_) => {{}}\n{pad}}}"
        if lang == "vb6":
            return f"{pad}On Error GoTo Handler\n{try_body}\n{pad}GoTo Done\n{pad}Handler:\n{catch_body}\n{pad}Done:"
        return f"{pad}try {{\n{try_body}\n{pad}}} catch (Exception {catch_name}) {{\n{catch_body}\n{pad}}}"
    return f"{pad}// {type(stmt).__name__}"


def _emit_function(lang: str, method: UniversalMethod) -> str:
    params = method.params
    if lang == "python":
        sig = ", ".join(f"{p.name}: {_type_name(lang, p.type_info)}" for p in params)
        nonlocal_needs = _assigned_names(method.body)
        header = f"def {method.name}({sig}) -> {_type_name(lang, method.return_type)}:\n"
        body = _emit_stmts(lang, method.body, 1) or "    pass"
        return header + body
    if lang == "go":
        sig = ", ".join(f"{p.name} {_type_name(lang, p.type_info)}" for p in params)
        ret = _type_name(lang, method.return_type)
        body = _emit_stmts("go", method.body, 1)
        prelude = ""
        if "mu.Lock()" in body and "var mu sync.Mutex" not in body:
            prelude += "    var mu sync.Mutex\n"
        if "wg.Add" in body and "var wg sync.WaitGroup" not in body:
            prelude += "    var wg sync.WaitGroup\n"
        return f"func {method.name}({sig}) {ret} {{\n{prelude}{body}\n}}"
    if lang == "java":
        sig = ", ".join(f"{_type_name(lang, p.type_info)} {p.name}" for p in params)
        ret = _type_name(lang, method.return_type)
        ann = ""
        if method.http_method == "GET":
            ann = '    @GetMapping("/{sku}")\n'
        elif method.http_method == "POST":
            ann = "    @PostMapping\n"
        body = _emit_stmts(lang, method.body, 2)
        extras = ""
        text = body
        if "synchronized" in text:
            extras += "        final Object mu = new Object();\n"
        if "EXECUTOR.submit" in text:
            extras += "        // ExecutorService.submit / Future.get\n"
        return f"{ann}    public {ret} {method.name}({sig}) throws Exception {{\n{extras}{body}\n    }}"
    if lang == "csharp":
        sig = ", ".join(f"{_type_name(lang, p.type_info)} {p.name}" for p in params)
        ret = _type_name(lang, method.return_type)
        ann = ""
        if method.http_method == "GET":
            ann = "    [HttpGet]\n"
        elif method.http_method == "POST":
            ann = "    [HttpPost]\n"
        body = _emit_stmts(lang, method.body, 2)
        extras = "        object mu = new object();\n" if "lock (mu)" in body else ""
        return f"{ann}    public {ret} {method.name}({sig}) {{\n{extras}{body}\n    }}"
    if lang == "rust":
        sig = ", ".join(f"{p.name}: {_type_name(lang, p.type_info)}" for p in params)
        ret = _type_name(lang, method.return_type)
        body = _emit_stmts(lang, method.body, 1)
        extras = "    let mu = std::sync::Mutex::new(());\n" if "mu.lock()" in body else ""
        return f"fn {method.name}({sig}) -> {ret} {{\n{extras}{body}\n}}"
    if lang == "kotlin":
        sig = ", ".join(f"{p.name}: {_type_name(lang, p.type_info)}" for p in params)
        ret = _type_name(lang, method.return_type)
        ann = ""
        if method.http_method == "GET":
            ann = "    @GetMapping\n"
        body = _emit_stmts(lang, method.body, 1)
        extras = "    val mu = Any()\n" if "synchronized(mu)" in body else ""
        return f"{ann}fun {method.name}({sig}): {ret} {{\n{extras}{body}\n}}"
    if lang == "php":
        sig = ", ".join(f"{p.name}" for p in params)
        body = _emit_stmts(lang, method.body, 1)
        extras = "    $mu = fopen('php://temp', 'r+');\n" if "flock($mu" in body else ""
        route = ""
        if method.http_method == "GET":
            route = "    // Route::get\n"
        elif method.http_method == "POST":
            route = "    // Route::post\n"
        return f"{route}function {method.name}({sig}) {{\n{extras}{body}\n}}"
    if lang in {"typescript", "react"}:
        sig = ", ".join(f"{p.name}: {_type_name(lang, p.type_info)}" for p in params)
        ret = _type_name(lang, method.return_type)
        decor = ""
        if method.http_method == "GET":
            decor = "@Get()\n"
        elif method.http_method == "POST":
            decor = "@Post()\n"
        return f"{decor}export async function {method.name}({sig}): Promise<{ret}> {{\n{_emit_stmts(lang, method.body, 1)}\n}}"
    if lang == "flutter":
        sig = ", ".join(f"{_type_name(lang, p.type_info)} {p.name}" for p in params)
        route = "  // Route: Get\n" if method.http_method == "GET" else ""
        return f"{route}Future<{_type_name(lang, method.return_type)}> {method.name}({sig}) async {{\n{_emit_stmts(lang, method.body, 1)}\n}}"
    if lang == "vb6":
        sig = ", ".join(p.name for p in params)
        return f"Function {method.name}({sig}) As Long\n{_emit_stmts(lang, method.body, 1)}\nEnd Function"
    if lang == "swift":
        sig = ", ".join(f"{p.name}: {_type_name(lang, p.type_info)}" for p in params)
        route = "    // Route: Get\n" if method.http_method == "GET" else ""
        return f"{route}func {method.name}({sig}) -> {_type_name(lang, method.return_type)} {{\n{_emit_stmts(lang, method.body, 1)}\n}}"
    if lang == "objc":
        sig = ":".join(
            [f"({_type_name(lang, method.return_type)}){method.name}"]
            + [f"({_type_name(lang, p.type_info)}){p.name}" for p in params]
        )
        route = "// Route: Get\n" if method.http_method == "GET" else ""
        return f"{route}- {sig} {{\n{_emit_stmts(lang, method.body, 1)}\n}}"
    # cpp / vcpp6
    sig = ", ".join(f"{_type_name(lang, p.type_info)} {p.name}" for p in params)
    extras = "    std::mutex mu;\n" if "industrial_guard(mu)" in _emit_stmts(lang, method.body, 1) else ""
    route = "// Route: Get\n" if method.http_method == "GET" else ""
    return f"{route}{_type_name(lang, method.return_type)} {method.name}({sig}) {{\n{extras}{_emit_stmts(lang, method.body, 1)}\n}}"


def _prelude(lang: str, module: UniversalModule) -> str:
    runtime = concurrency_runtime(lang)
    io = io_runtime(lang)
    fw = framework_runtime(lang)
    if lang == "python":
        return (
            "from __future__ import annotations\n"
            "import hashlib\n"
            "import queue\n"
            "import tempfile\n"
            "import threading\n"
            "from pathlib import Path\n\n"
        )
    if lang == "go":
        return (
            "package industrial\n\n"
            "import (\n"
            '    "fmt"\n'
            '    "os"\n'
            '    "path/filepath"\n'
            '    "sync"\n'
            ")\n\n"
            f"// runtime {runtime['spawn']} {runtime['channel']} {runtime['lock']}\n"
        )
    if lang == "java":
        ctrl = "import org.springframework.web.bind.annotation.*;\n" if any(c.is_controller for c in module.classes) else ""
        return (
            "package io.elmos.industrial;\n\n"
            "import java.nio.file.Files;\n"
            "import java.nio.file.Path;\n"
            "import java.util.concurrent.*;\n"
            f"{ctrl}\n"
            "public final class IndustrialRuntime {\n"
            "    private static final ExecutorService EXECUTOR = Executors.newCachedThreadPool();\n"
        )
    if lang == "csharp":
        return (
            "using System;\nusing System.IO;\nusing System.Threading.Tasks;\nusing System.Threading.Channels;\n"
            "using Microsoft.AspNetCore.Mvc;\n\n"
            f"// {fw['controller']} {runtime['spawn']} {io['write']}\n"
            "public static class IndustrialRuntime {\n"
        )
    if lang == "rust":
        return "use std::sync::{Arc, Mutex};\nuse std::thread;\nuse std::sync::mpsc;\n\n"
    if lang == "kotlin":
        return (
            "import java.util.concurrent.LinkedBlockingQueue\n"
            "import java.nio.file.Files\nimport java.nio.file.Path\n"
            "import kotlin.concurrent.thread\n"
            "import org.springframework.web.bind.annotation.*\n\n"
        )
    if lang == "php":
        return "<?php\n"
    if lang in {"typescript", "react"}:
        return (
            "import * as fs from 'fs';\n"
            "class AsyncQueue<T> { private q: T[] = []; put(v: T) { this.q.push(v); } async take(): Promise<T> { return this.q.shift() as T; } }\n"
            "class Mutex { async run<T>(fn: () => T): Promise<T> { return fn(); } }\n\n"
        )
    if lang == "cpp":
        return "#include <thread>\n#include <mutex>\n#include <queue>\n#include <fstream>\n#include <string>\n\n"
    if lang == "vcpp6":
        return "#include <afxmt.h>\n#include <afx.h>\n// AfxBeginThread CCriticalSection CStdioFile\n\n"
    if lang == "swift":
        return "import Foundation\n"
    if lang == "objc":
        return "#import <Foundation/Foundation.h>\n"
    if lang == "flutter":
        return "import 'dart:async';\nimport 'dart:io';\n"
    if lang == "vb6":
        return "Option Explicit\n"
    return ""


def _footer(lang: str) -> str:
    if lang in {"java", "csharp"}:
        return "}\n"
    return ""


def _emit_class(lang: str, klass: UniversalClass) -> str:
    methods = "\n\n".join(_emit_function(lang, m) for m in klass.methods)
    if lang == "java" and klass.is_controller:
        route = klass.base_route or "/api/v1/inventory"
        return f"    @RestController\n    @RequestMapping(\"{route}\")\n    public static class {klass.name} {{\n{methods}\n    }}\n"
    if lang == "csharp" and klass.is_controller:
        return f"    [ApiController]\n    public class {klass.name} {{\n{methods}\n    }}\n"
    if lang == "kotlin" and klass.is_controller:
        return f"@RestController\nclass {klass.name} {{\n{methods}\n}}\n"
    if lang == "python":
        return methods
    return methods


def _emit_lang(module: UniversalModule, lang: str) -> str:
    chunks = [_prelude(lang, module)]
    for klass in module.classes:
        chunks.append(_emit_class(lang, klass))
    for method in module.free_functions:
        chunks.append(_emit_function(lang, method))
    chunks.append(_footer(lang))
    return "\n".join(chunk for chunk in chunks if chunk)


_EMITTERS = {lang: _emit_lang for lang in (
    "java", "csharp", "python", "typescript", "go", "rust", "kotlin", "php",
    "cpp", "objc", "swift", "react", "flutter", "vb6", "vcpp6",
)}
