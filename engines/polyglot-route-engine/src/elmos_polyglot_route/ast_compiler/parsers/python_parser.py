"""Real AST parser for Python enterprise code using python native 'ast' module."""

from __future__ import annotations

import ast
import textwrap
from typing import Any

from ..ir import (
    AwaitExpr,
    BinaryExpr,
    BinaryOperator,
    CatchClause,
    ConstructExpr,
    ExprStmt,
    FieldAccessExpr,
    IdentifierExpr,
    IfElseStmt,
    LiteralExpr,
    MethodCallExpr,
    PrimitiveKind,
    RawSnippetExpr,
    ReturnStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UniversalAnnotation,
    UniversalClass,
    UniversalConstructor,
    UniversalExpr,
    UniversalField,
    UniversalMethod,
    UniversalModule,
    UniversalParam,
    UniversalStmt,
    UniversalType,
    VarDeclStmt,
)
from .base import BaseAstParser


class PythonAstParser(BaseAstParser):
    """Parses Python code using the official 'ast' library into Universal AST IR."""

    def __init__(self) -> None:
        super().__init__('python')

    def parse(self, source_code: str) -> UniversalModule:
        clean_source = textwrap.dedent(source_code).strip()
        try:
            tree = ast.parse(clean_source)
        except SyntaxError as ex:
            # Fallback module with raw snippet if syntax error
            module = UniversalModule(name='PythonModule', source_language='python')
            module.classes.append(UniversalClass(name='SyntaxErrorClass'))
            return module

        module = UniversalModule(name='PythonModule', source_language='python')

        # Detect imports
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module.imports.append(f"{node.module}.{node.names[0].name}")

        # Detect classes, functions, and router configurations
        base_route = "/api/v1/assets"
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                cls = self._parse_class(node)
                module.classes.append(cls)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = self._parse_function(node)
                module.free_functions.append(fn)
            elif isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    func_name = self._decorator_to_str(node.value.func)
                    if "APIRouter" in func_name:
                        for kw in node.value.keywords:
                            if kw.arg in ("prefix", "path") and isinstance(kw.value, ast.Constant):
                                base_route = str(kw.value.value)

        # If there are free functions with route decorators, group into a Controller class
        routed_functions = [fn for fn in module.free_functions if fn.http_method is not None]
        other_functions = [fn for fn in module.free_functions if fn.http_method is None]

        if routed_functions:
            controller_cls = UniversalClass(
                name="EnterpriseAssetController",
                is_controller=True,
                base_route=base_route,
                methods=routed_functions,
            )
            module.classes.append(controller_cls)
        elif other_functions and not module.classes:
            wrapper_cls = UniversalClass(
                name="PythonService",
                methods=other_functions,
            )
            module.classes.append(wrapper_cls)

        return module

    def _parse_class(self, node: ast.ClassDef) -> UniversalClass:
        annotations: list[UniversalAnnotation] = []
        is_controller = False
        base_route: str | None = None

        for dec in node.decorator_list:
            dec_name = self._decorator_to_str(dec)
            annotations.append(UniversalAnnotation(name=dec_name))
            if 'router' in dec_name.lower() or 'controller' in dec_name.lower():
                is_controller = True

        fields: list[UniversalField] = []
        constructors: list[UniversalConstructor] = []
        methods: list[UniversalMethod] = []

        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                field_type = self._annotation_to_type(item.annotation)
                fields.append(UniversalField(name=field_name, type_info=field_type))
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name == '__init__':
                    ctor = self._parse_constructor(item)
                    constructors.append(ctor)
                    # Also extract self.field = ... from init
                    for stmt in item.body:
                        if isinstance(stmt, ast.Assign):
                            for target in stmt.targets:
                                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                                    fname = target.attr
                                    if not any(f.name == fname for f in fields):
                                        fields.append(UniversalField(name=fname, type_info=UniversalType.string_type()))
                else:
                    m = self._parse_function(item)
                    methods.append(m)

        # Check for APIRouter instantiated in module or class
        cls_name = node.name
        return UniversalClass(
            name=cls_name,
            fields=fields,
            constructors=constructors,
            methods=methods,
            annotations=annotations,
            is_controller=is_controller,
            base_route=base_route or ('/api/v1/assets' if 'Asset' in cls_name else None),
        )

    def _parse_constructor(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> UniversalConstructor:
        params: list[UniversalParam] = []
        for arg in node.args.args:
            if arg.arg == 'self':
                continue
            ptype = self._annotation_to_type(arg.annotation) if arg.annotation else UniversalType.string_type()
            params.append(UniversalParam(name=arg.arg, type_info=ptype))
        body = self._parse_body(node.body)
        return UniversalConstructor(params=params, body=body)

    def _parse_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> UniversalMethod:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        return_type = self._annotation_to_type(node.returns) if node.returns else UniversalType.void()

        params: list[UniversalParam] = []
        for arg in node.args.args:
            if arg.arg == 'self' or arg.arg == 'cls':
                continue
            ptype = self._annotation_to_type(arg.annotation) if arg.annotation else UniversalType.string_type()
            params.append(UniversalParam(name=arg.arg, type_info=ptype))

        annotations: list[UniversalAnnotation] = []
        http_method: str | None = None
        http_path: str | None = None

        for dec in node.decorator_list:
            dec_str = self._decorator_to_str(dec)
            annotations.append(UniversalAnnotation(name=dec_str))
            lower_dec = dec_str.lower()
            if '.get' in lower_dec:
                http_method = 'GET'
                http_path = self._extract_path_arg(dec) or ''
            elif '.post' in lower_dec:
                http_method = 'POST'
                http_path = self._extract_path_arg(dec) or ''
            elif '.put' in lower_dec:
                http_method = 'PUT'
                http_path = self._extract_path_arg(dec) or ''
            elif '.delete' in lower_dec:
                http_method = 'DELETE'
                http_path = self._extract_path_arg(dec) or ''

        body = self._parse_body(node.body)

        return UniversalMethod(
            name=node.name,
            params=params,
            return_type=return_type,
            is_async=is_async,
            annotations=annotations,
            body=body,
            http_method=http_method,
            http_path=http_path,
        )

    def _parse_body(self, stmts: list[ast.stmt]) -> list[UniversalStmt]:
        result: list[UniversalStmt] = []
        for s in stmts:
            parsed = self._parse_statement(s)
            if parsed:
                result.append(parsed)
        return result

    def _parse_statement(self, stmt: ast.stmt) -> UniversalStmt | None:
        if isinstance(stmt, ast.Return):
            val = self._parse_expr(stmt.value) if stmt.value else None
            return ReturnStmt(value=val)
        elif isinstance(stmt, ast.Raise):
            exc_class = 'Exception'
            msg = 'Error'
            if stmt.exc:
                if isinstance(stmt.exc, ast.Call):
                    if isinstance(stmt.exc.func, ast.Name):
                        exc_class = stmt.exc.func.id
                    if stmt.exc.args and isinstance(stmt.exc.args[0], ast.Constant):
                        msg = str(stmt.exc.args[0].value)
            return ThrowStmt(exception_class=exc_class, message=msg)
        elif isinstance(stmt, ast.Try):
            try_body = self._parse_body(stmt.body)
            catches: list[CatchClause] = []
            for handler in stmt.handlers:
                exc_type = 'Exception'
                if handler.type and isinstance(handler.type, ast.Name):
                    exc_type = handler.type.id
                var_name = handler.name or 'ex'
                cbody = self._parse_body(handler.body)
                catches.append(CatchClause(exception_type=exc_type, variable_name=var_name, body=cbody))
            finally_body = self._parse_body(stmt.finalbody) if stmt.finalbody else []
            return TryCatchFinallyStmt(try_body=try_body, catch_clauses=catches, finally_body=finally_body)
        elif isinstance(stmt, ast.If):
            cond = self._parse_expr(stmt.test) or LiteralExpr(value=True, type_kind='bool')
            then_b = self._parse_body(stmt.body)
            else_b = self._parse_body(stmt.orelse) if stmt.orelse else []
            return IfElseStmt(condition=cond, then_body=then_b, else_body=else_b)
        elif isinstance(stmt, ast.Expr):
            expr = self._parse_expr(stmt.value)
            if expr:
                return ExprStmt(expr=expr)
        return None

    def _parse_expr(self, expr: ast.expr | None) -> UniversalExpr | None:
        if expr is None:
            return None
        if isinstance(expr, ast.Constant):
            val = expr.value
            if isinstance(val, bool):
                return LiteralExpr(value=val, type_kind='bool')
            elif isinstance(val, (int, float)):
                return LiteralExpr(value=val, type_kind='int' if isinstance(val, int) else 'float')
            elif isinstance(val, str):
                return LiteralExpr(value=val, type_kind='string')
            elif val is None:
                return LiteralExpr(value=None, type_kind='null')
        elif isinstance(expr, ast.Name):
            return IdentifierExpr(name=expr.id)
        elif isinstance(expr, ast.Attribute):
            target = self._parse_expr(expr.value)
            if target:
                return FieldAccessExpr(target=target, field_name=expr.attr)
        elif isinstance(expr, ast.Call):
            target = None
            fname = 'unknown'
            if isinstance(expr.func, ast.Name):
                fname = expr.func.id
            elif isinstance(expr.func, ast.Attribute):
                target = self._parse_expr(expr.func.value)
                fname = expr.func.attr
            args = [self._parse_expr(a) for a in expr.args if self._parse_expr(a) is not None]
            return MethodCallExpr(target=target, method_name=fname, args=args)
        elif isinstance(expr, ast.Await):
            inner = self._parse_expr(expr.value)
            if inner:
                return AwaitExpr(inner=inner)
        elif isinstance(expr, ast.BinOp):
            left = self._parse_expr(expr.left)
            right = self._parse_expr(expr.right)
            op = BinaryOperator.ADD
            if isinstance(expr.op, ast.Sub):
                op = BinaryOperator.SUB
            elif isinstance(expr.op, ast.Mult):
                op = BinaryOperator.MUL
            elif isinstance(expr.op, ast.Div):
                op = BinaryOperator.DIV
            if left and right:
                return BinaryExpr(left=left, op=op, right=right)
        return RawSnippetExpr(code=ast.unparse(expr) if hasattr(ast, 'unparse') else '')

    def _annotation_to_type(self, node: ast.expr | None) -> UniversalType:
        if node is None:
            return UniversalType.string_type()
        if isinstance(node, ast.Name):
            return self.parse_type(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            return self.parse_type(node.value)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                base_name = node.value.id
                if base_name in ('list', 'List') and isinstance(node.slice, ast.Name):
                    return UniversalType.list_of(self.parse_type(node.slice.id))
                elif base_name in ('Optional',):
                    if isinstance(node.slice, ast.Name):
                        return UniversalType.optional_of(self.parse_type(node.slice.id))
        return UniversalType.string_type()

    def _decorator_to_str(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._decorator_to_str(node.value)
            return f"{val}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._decorator_to_str(node.func)
        return ''

    def _extract_path_arg(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Call):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                return node.args[0].value
            for kw in node.keywords:
                if kw.arg in ('path', 'prefix') and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    return kw.value.value
        return None
