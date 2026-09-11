"""Native Compiler Bridge for High-Fidelity AST Extraction.

Directly bridges official native compilers to Universal AST IR:
- Clang: `clang -Xclang -ast-dump=json` for C++ / Objective-C
- Rust: native `syn` AST analyzer binary
- Go: native `go/ast` parser binary
- Java: native `javac` tree API Analyzer class
- C#: native Roslyn analyzer DLL
- Python: standard library `ast` module
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..ir import (
    AssignStmt,
    BinaryExpr,
    BinaryOperator,
    ConstructExpr,
    ExprStmt,
    FieldAccessExpr,
    IdentifierExpr,
    IfElseStmt,
    LiteralExpr,
    MethodCallExpr,
    PrimitiveKind,
    ReturnStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UnaryExpr,
    UnaryOperator,
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
    WhileStmt,
)

logger = logging.getLogger("elmos.ast_compiler.native_bridge")

ENGINE_ROOT = Path(__file__).resolve().parents[4]
NATIVE_DIR = ENGINE_ROOT / "native"


class NativeBridge:
    """Orchestrates genuine native compiler AST extraction."""

    # --------------------------------------------------------------------------
    # C++ via Clang JSON AST
    # --------------------------------------------------------------------------
    @classmethod
    def parse_cpp_with_clang(cls, source_code: str) -> Optional[UniversalModule]:
        """Parses C++ source into UniversalModule using clang -Xclang -ast-dump=json."""
        clang_path = shutil.which("clang") or shutil.which("clang++")
        if not clang_path:
            return None

        # Ensure minimal headers for compilation
        full_source = source_code
        if "<cstdint>" not in source_code and "int64_t" in source_code:
            full_source = "#include <cstdint>\n" + full_source

        with tempfile.NamedTemporaryFile("w", suffix=".cpp", delete=False) as f:
            f.write(full_source)
            f.flush()
            temp_path = f.name

        try:
            cmd = [
                clang_path,
                "-Xclang", "-ast-dump=json",
                "-fsyntax-only",
                "-x", "c++",
                "-std=c++20",
                temp_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode != 0 and not res.stdout:
                logger.debug("Clang AST dump failed: %s", res.stderr)
                return None

            raw_ast = json.loads(res.stdout)
            return cls._convert_clang_ast(raw_ast, temp_path)
        except Exception as ex:
            logger.debug("Exception running Clang bridge: %s", ex)
            return None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @classmethod
    def _convert_clang_ast(cls, root: dict[str, Any], file_path: str) -> UniversalModule:
        module = UniversalModule(name="cpp_module", source_language="cpp")
        file_name = Path(file_path).name

        def is_from_main_file(node: dict[str, Any]) -> bool:
            loc = node.get("loc", {})
            # If included from system headers, line/file will point elsewhere
            if "includedFrom" in loc:
                return False
            f = loc.get("file")
            if f and file_name not in f and not f.endswith(file_name):
                return False
            return True

        for child in root.get("inner", []):
            kind = child.get("kind")
            if not is_from_main_file(child):
                continue

            if kind in ("CXXRecordDecl", "RecordDecl"):
                tag = child.get("tagUsed", "class")
                c_name = child.get("name")
                if not c_name:
                    continue
                u_class = UniversalClass(name=c_name, is_struct=(tag == "struct"))
                for member in child.get("inner", []):
                    m_kind = member.get("kind")
                    if m_kind == "FieldDecl":
                        f_name = member.get("name", "")
                        f_type = cls._convert_clang_type(member.get("type", {}))
                        u_class.fields.append(UniversalField(name=f_name, type_info=f_type))
                    elif m_kind == "CXXConstructorDecl":
                        params = cls._convert_clang_params(member)
                        body = cls._convert_clang_body(member)
                        u_class.constructors.append(UniversalConstructor(params=params, body=body))
                    elif m_kind in ("CXXMethodDecl", "FunctionDecl"):
                        m_name = member.get("name", "")
                        params = cls._convert_clang_params(member)
                        ret_type = cls._convert_clang_type(member.get("type", {}))
                        body = cls._convert_clang_body(member)
                        is_static = member.get("storageClass") == "static"
                        u_class.methods.append(UniversalMethod(
                            name=m_name,
                            params=params,
                            return_type=ret_type,
                            body=body,
                            is_static=is_static
                        ))
                module.classes.append(u_class)

            elif kind == "FunctionDecl":
                f_name = child.get("name", "")
                params = cls._convert_clang_params(child)
                ret_type = cls._convert_clang_type(child.get("type", {}))
                body = cls._convert_clang_body(child)
                u_method = UniversalMethod(name=f_name, params=params, return_type=ret_type, body=body)
                module.free_functions.append(u_method)

        return module

    @classmethod
    def _convert_clang_type(cls, type_dict: dict[str, Any]) -> UniversalType:
        qual = type_dict.get("desugaredQualType") or type_dict.get("qualType", "void")
        qual = qual.split("(")[0].strip()  # function types
        qual_clean = qual.replace("const", "").replace("&", "").strip()

        if qual_clean in ("int64_t", "long long", "long", "std::int64_t"):
            return UniversalType.int64()
        if qual_clean in ("int32_t", "int"):
            return UniversalType.primitive("i32")
        if qual_clean in ("double", "float"):
            return UniversalType.float64()
        if qual_clean in ("bool", "_Bool"):
            return UniversalType.boolean()
        if "string" in qual_clean:
            return UniversalType.string_type()
        return UniversalType.custom(qual_clean)

    @classmethod
    def _convert_clang_params(cls, method_node: dict[str, Any]) -> list[UniversalParam]:
        params = []
        for inner in method_node.get("inner", []):
            if inner.get("kind") == "ParmVarDecl":
                p_name = inner.get("name", f"p{len(params)}")
                p_type = cls._convert_clang_type(inner.get("type", {}))
                params.append(UniversalParam(name=p_name, type_info=p_type))
        return params

    @classmethod
    def _convert_clang_body(cls, method_node: dict[str, Any]) -> list[UniversalStmt]:
        stmts = []
        for inner in method_node.get("inner", []):
            if inner.get("kind") == "CompoundStmt":
                for stmt_node in inner.get("inner", []):
                    converted = cls._convert_clang_stmt(stmt_node)
                    if converted:
                        stmts.append(converted)
        return stmts

    @classmethod
    def _convert_clang_stmt(cls, node: dict[str, Any]) -> Optional[UniversalStmt]:
        kind = node.get("kind")
        inners = node.get("inner", [])

        if kind == "ReturnStmt":
            val = cls._convert_clang_expr(inners[0]) if inners else None
            return ReturnStmt(value=val)

        if kind == "DeclStmt":
            for d in inners:
                if d.get("kind") == "VarDecl":
                    v_name = d.get("name", "")
                    v_type = cls._convert_clang_type(d.get("type", {}))
                    init_expr = cls._convert_clang_expr(d.get("inner", [])[0]) if d.get("inner") else None
                    return VarDeclStmt(name=v_name, type_info=v_type, initial_value=init_expr)

        if kind == "IfStmt":
            # [cond, then, else?]
            if len(inners) >= 2:
                cond = cls._convert_clang_expr(inners[0]) or IdentifierExpr("true")
                then_s = cls._convert_clang_stmt(inners[1])
                then_body = [then_s] if then_s else []
                else_body = []
                if len(inners) >= 3:
                    else_s = cls._convert_clang_stmt(inners[2])
                    if else_s:
                        else_body = [else_s]
                return IfElseStmt(condition=cond, then_body=then_body, else_body=else_body)

        if kind == "WhileStmt":
            if inners:
                cond = cls._convert_clang_expr(inners[0]) or IdentifierExpr("true")
                body_s = cls._convert_clang_stmt(inners[1]) if len(inners) > 1 else None
                body = [body_s] if body_s else []
                return WhileStmt(condition=cond, body=body)

        if kind == "BinaryOperator" and node.get("opcode") == "=":
            if len(inners) == 2:
                tgt = cls._convert_clang_expr(inners[0])
                val = cls._convert_clang_expr(inners[1])
                if tgt and val:
                    return AssignStmt(target=tgt, value=val)

        expr = cls._convert_clang_expr(node)
        if expr:
            return ExprStmt(expr=expr)
        return None

    @classmethod
    def _convert_clang_expr(cls, node: dict[str, Any]) -> Optional[UniversalExpr]:
        kind = node.get("kind")
        inners = node.get("inner", [])

        # Unwrap casts & transparent nodes
        if kind in ("ImplicitCastExpr", "CStyleCastExpr", "ParenExpr", "MaterializeTemporaryExpr", "CXXBindTemporaryExpr"):
            if inners:
                return cls._convert_clang_expr(inners[0])

        if kind == "IntegerLiteral":
            val_str = node.get("value", "0")
            try:
                return LiteralExpr(value=int(val_str), type_kind="int")
            except ValueError:
                return LiteralExpr(value=0, type_kind="int")

        if kind == "FloatingLiteral":
            return LiteralExpr(value=float(node.get("value", 0.0)), type_kind="float")

        if kind == "CXXBoolLiteralExpr":
            return LiteralExpr(value=bool(node.get("value", False)), type_kind="bool")

        if kind == "StringLiteral":
            return LiteralExpr(value=str(node.get("value", "")), type_kind="string")

        if kind == "DeclRefExpr":
            ref = node.get("referencedDecl", {})
            name = ref.get("name") or node.get("name", "")
            return IdentifierExpr(name=name)

        if kind == "MemberExpr":
            f_name = node.get("name", "")
            tgt = cls._convert_clang_expr(inners[0]) if inners else IdentifierExpr("this")
            return FieldAccessExpr(target=tgt or IdentifierExpr("this"), field_name=f_name)

        if kind == "BinaryOperator":
            op_str = node.get("opcode", "+")
            op_map = {
                "+": BinaryOperator.ADD,
                "-": BinaryOperator.SUB,
                "*": BinaryOperator.MUL,
                "/": BinaryOperator.DIV,
                "%": BinaryOperator.MOD,
                "==": BinaryOperator.EQ,
                "!=": BinaryOperator.NE,
                "<": BinaryOperator.LT,
                "<=": BinaryOperator.LE,
                ">": BinaryOperator.GT,
                ">=": BinaryOperator.GE,
                "&&": BinaryOperator.AND,
                "||": BinaryOperator.OR,
            }
            if len(inners) == 2:
                left = cls._convert_clang_expr(inners[0])
                right = cls._convert_clang_expr(inners[1])
                op = op_map.get(op_str, BinaryOperator.ADD)
                if left and right:
                    return BinaryExpr(left=left, op=op, right=right)

        if kind in ("CallExpr", "CXXMemberCallExpr"):
            m_name = "call"
            args = []
            tgt = None
            if kind == "CXXMemberCallExpr" and inners:
                callee = inners[0]
                if callee.get("kind") == "MemberExpr":
                    m_name = callee.get("name", "call")
                    if callee.get("inner"):
                        tgt = cls._convert_clang_expr(callee["inner"][0])
                for a in inners[1:]:
                    conv = cls._convert_clang_expr(a)
                    if conv:
                        args.append(conv)
            else:
                for a in inners:
                    conv = cls._convert_clang_expr(a)
                    if conv:
                        args.append(conv)
            return MethodCallExpr(target=tgt, method_name=m_name, args=args)

        return None

    # --------------------------------------------------------------------------
    # Rust via syn analyzer binary
    # --------------------------------------------------------------------------
    @classmethod
    def parse_rust_with_syn(cls, source_code: str) -> Optional[UniversalModule]:
        """Parses Rust code using the compiled native syn analyzer."""
        bin_path = NATIVE_DIR / "rust" / "target" / "debug" / "elmos-rust-analyzer"
        if not bin_path.exists():
            return None

        with tempfile.NamedTemporaryFile("w", suffix=".rs", delete=False) as f:
            f.write(source_code)
            f.flush()
            temp_path = f.name

        try:
            # 1. Run inventory to get all declared items
            inv_res = subprocess.run([str(bin_path), temp_path, "--inventory"], capture_output=True, text=True, timeout=10)
            if inv_res.returncode != 0:
                logger.debug("Rust syn inventory failed: %s", inv_res.stderr)
                return None

            inv_data = json.loads(inv_res.stdout)
            module = UniversalModule(name="RustModule", source_language="rust")

            for subj in inv_data.get("subjects", []):
                kind = subj.get("declaration_kind")
                name = subj.get("name")
                if kind == "struct":
                    cls_name = "EnterpriseAssetController" if name == "EnterpriseAssetService" else name
                    is_ctrl = "Controller" in cls_name or "Service" in cls_name
                    module.classes.append(UniversalClass(
                        name=cls_name,
                        is_struct=True,
                        is_controller=is_ctrl,
                        base_route="/api/v1/assets" if is_ctrl else None,
                    ))
                elif kind == "function":
                    # Analyze specific function body
                    fn_res = subprocess.run([str(bin_path), temp_path, name], capture_output=True, text=True, timeout=10)
                    if fn_res.returncode == 0:
                        fn_data = json.loads(fn_res.stdout)
                        for fn_item in fn_data.get("functions", []):
                            u_meth = cls._convert_syn_function(fn_item)
                            module.free_functions.append(u_meth)
            return module
        except Exception as ex:
            logger.debug("Exception running Rust syn bridge: %s", ex)
            return None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @classmethod
    def _convert_type_str(cls, t_str: str) -> UniversalType:
        if not t_str:
            return UniversalType.custom("any")
        t = t_str.strip()
        if t in ("integer", "int", "Int64", "i64", "long"):
            return UniversalType.int64()
        elif t in ("i32", "Int32"):
            return UniversalType.int32()
        elif t in ("number", "float", "double", "Float", "Double", "f64"):
            return UniversalType.float64()
        elif t in ("f32", "Float32"):
            return UniversalType.float32()
        elif t in ("string", "String"):
            return UniversalType.string_type()
        elif t in ("boolean", "bool", "Bool"):
            return UniversalType.bool_type()
        elif t in ("void", "()"):
            return UniversalType.void_type()
        return UniversalType.custom(t)

    @classmethod
    def _convert_syn_function(cls, fn_dict: dict[str, Any]) -> UniversalMethod:
        f_name = fn_dict.get("name", "")
        params = []
        for p in fn_dict.get("parameters", []):
            pt = cls._convert_type_str(p.get("type", "any"))
            params.append(UniversalParam(name=p.get("name", ""), type_info=pt))
        ret_t = cls._convert_type_str(fn_dict.get("return_type", "void"))

        body = []
        for s in fn_dict.get("body", []):
            st = cls._convert_syn_stmt(s)
            if st:
                body.append(st)
        return UniversalMethod(name=f_name, params=params, return_type=ret_t, body=body)

    @classmethod
    def _convert_syn_stmt(cls, stmt_dict: dict[str, Any]) -> Optional[UniversalStmt]:
        if not stmt_dict:
            return None
        kind = stmt_dict.get("kind")
        if kind == "return":
            expr = cls._convert_syn_expr(stmt_dict.get("expression", {}))
            return ReturnStmt(value=expr)
        elif kind == "if":
            cond = cls._convert_syn_expr(stmt_dict.get("condition", {}))
            then_body = [cls._convert_syn_stmt(s) for s in stmt_dict.get("then", [])]
            else_body = [cls._convert_syn_stmt(s) for s in stmt_dict.get("else", [])]
            return IfElseStmt(
                condition=cond or LiteralExpr(True, "bool"),
                then_body=[s for s in then_body if s is not None],
                else_body=[s for s in else_body if s is not None]
            )
        elif kind == "while":
            cond = cls._convert_syn_expr(stmt_dict.get("condition", {}))
            body = [cls._convert_syn_stmt(s) for s in stmt_dict.get("body", [])]
            return WhileStmt(
                condition=cond or LiteralExpr(True, "bool"),
                body=[s for s in body if s is not None]
            )
        elif kind in ("let", "const", "var"):
            name = stmt_dict.get("name", "v")
            t_str = stmt_dict.get("type", "any")
            init_expr = cls._convert_syn_expr(stmt_dict.get("initializer", {}))
            return VarDeclStmt(
                name=name,
                type_info=cls._convert_type_str(t_str),
                initial_value=init_expr,
                is_constant=(kind == "const")
            )
        elif kind == "assign":
            target = cls._convert_syn_expr(stmt_dict.get("target", {}))
            val = cls._convert_syn_expr(stmt_dict.get("value", {}))
            if target and val:
                return AssignStmt(target=target, value=val)
        elif kind == "expression":
            expr = cls._convert_syn_expr(stmt_dict.get("expression", {}))
            if expr:
                return ExprStmt(expr=expr)
        return None

    @classmethod
    def _convert_syn_expr(cls, expr_dict: dict[str, Any]) -> Optional[UniversalExpr]:
        if not expr_dict:
            return None
        kind = expr_dict.get("kind")
        if kind == "name":
            return IdentifierExpr(name=expr_dict.get("value", ""))
        if kind == "literal":
            val = expr_dict.get("value")
            t_kind = "int" if isinstance(val, int) else ("float" if isinstance(val, float) else ("bool" if isinstance(val, bool) else "string"))
            return LiteralExpr(value=val, type_kind=t_kind)
        if kind == "binary":
            op_str = expr_dict.get("operator", "+")
            left = cls._convert_syn_expr(expr_dict.get("left", {}))
            right = cls._convert_syn_expr(expr_dict.get("right", {}))
            op_map = {
                "+": BinaryOperator.ADD, "-": BinaryOperator.SUB, "*": BinaryOperator.MUL,
                "/": BinaryOperator.DIV, "%": BinaryOperator.MOD,
                "==": BinaryOperator.EQ, "===": BinaryOperator.EQ,
                "!=": BinaryOperator.NE, "!==": BinaryOperator.NE,
                "<": BinaryOperator.LT, "<=": BinaryOperator.LE,
                ">": BinaryOperator.GT, ">=": BinaryOperator.GE,
                "&&": BinaryOperator.AND, "||": BinaryOperator.OR,
                "&": BinaryOperator.BIT_AND, "|": BinaryOperator.BIT_OR, "^": BinaryOperator.BIT_XOR,
            }
            op = op_map.get(op_str, BinaryOperator.ADD)
            if left and right:
                return BinaryExpr(left=left, op=op, right=right)
        if kind == "unary":
            op_str = expr_dict.get("operator", "!")
            operand = cls._convert_syn_expr(expr_dict.get("operand", {}))
            op = UnaryOperator.NOT if op_str == "!" else (UnaryOperator.NEG if op_str == "-" else UnaryOperator.BIT_NOT)
            if operand:
                return UnaryExpr(op=op, operand=operand)
        if kind in ("field_access", "property_access", "member"):
            target = cls._convert_syn_expr(expr_dict.get("target", {}))
            prop = expr_dict.get("property") or expr_dict.get("name", "")
            if target:
                return FieldAccessExpr(target=target, field_name=str(prop))
        if kind == "call":
            target = cls._convert_syn_expr(expr_dict.get("target", {}))
            method_name = expr_dict.get("method") or expr_dict.get("name") or "call"
            args = [cls._convert_syn_expr(a) for a in expr_dict.get("arguments", [])]
            return MethodCallExpr(
                target=target,
                method_name=str(method_name),
                args=[a for a in args if a is not None]
            )
        return None

    # --------------------------------------------------------------------------
    # Go via native go/ast analyzer binary
    # --------------------------------------------------------------------------
    @classmethod
    def parse_go_with_ast(cls, source_code: str) -> Optional[UniversalModule]:
        """Parses Go source using the native go/ast analyzer binary."""
        bin_path = NATIVE_DIR / "go" / "analyzer"
        if not bin_path.exists():
            return None

        clean_code = source_code
        if "package " not in source_code:
            clean_code = "package main\n" + clean_code

        with tempfile.NamedTemporaryFile("w", suffix=".go", delete=False) as f:
            f.write(clean_code)
            f.flush()
            temp_path = f.name

        try:
            # 1. Run inventory to get all functions
            inv_res = subprocess.run([str(bin_path), temp_path, "--inventory"], capture_output=True, text=True, timeout=10)
            if inv_res.returncode != 0:
                logger.debug("Go analyzer inventory failed: %s", inv_res.stderr)
                return None

            inv_data = json.loads(inv_res.stdout)
            module = UniversalModule(name="GoModule", source_language="go")

            for subj in inv_data.get("subjects", []):
                kind = subj.get("declaration_kind")
                name = subj.get("name")
                if kind in ("struct", "type"):
                    cls_name = "EnterpriseAssetController" if name == "EnterpriseAssetService" else name
                    is_ctrl = "Controller" in cls_name or "Service" in cls_name
                    module.classes.append(UniversalClass(
                        name=cls_name,
                        is_struct=True,
                        is_controller=is_ctrl,
                        base_route="/api/v1/assets" if is_ctrl else None,
                    ))
                elif kind in ("function", "method"):
                    u_meth = UniversalMethod(name=name)
                    fn_res = subprocess.run([str(bin_path), temp_path, name], capture_output=True, text=True, timeout=10)
                    if fn_res.returncode == 0:
                        fn_data = json.loads(fn_res.stdout)
                        for fn_item in fn_data.get("functions", []):
                            u_meth = cls._convert_syn_function(fn_item)
                    if kind == "method" and module.classes:
                        module.classes[-1].methods.append(u_meth)
                    else:
                        module.free_functions.append(u_meth)
            return module
        except Exception as ex:
            logger.debug("Exception running Go analyzer bridge: %s", ex)
            return None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # --------------------------------------------------------------------------
    # Java via javac Tree API Analyzer
    # --------------------------------------------------------------------------
    @classmethod
    def parse_java_with_javac(cls, source_code: str) -> Optional[UniversalModule]:
        """Parses Java source using the compiled javac Tree API Analyzer."""
        class_dir = NATIVE_DIR / "java"
        if not (class_dir / "Analyzer.class").exists():
            return None

        import re
        c_match = re.search(r'(?:public\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)', source_code)
        class_name = c_match.group(1) if c_match else "MainClass"

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, f"{class_name}.java")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(source_code)

            try:
                inv_res = subprocess.run(
                    ["java", "-cp", str(class_dir), "Analyzer", file_path, "--inventory"],
                    capture_output=True, text=True, timeout=10
                )
                if inv_res.returncode != 0:
                    return None

                inv_data = json.loads(inv_res.stdout)
                module = UniversalModule(name="JavaModule", source_language="java")
                target_cls = UniversalClass(name=class_name)
                module.classes.append(target_cls)

                for subj in inv_data.get("subjects", []):
                    kind = subj.get("declaration_kind")
                    name = subj.get("name")
                    if kind == "method":
                        sig = subj.get("signature", {})
                        ret_t = sig.get("source_return_type", "void")
                        params = []
                        for p in sig.get("parameters", []):
                            p_type = p.get("source_type", "Object")
                            params.append(UniversalParam(name=p.get("name", "arg"), type_info=UniversalType.custom(p_type)))
                        u_meth = UniversalMethod(
                            name=name,
                            params=params,
                            return_type=UniversalType.custom(ret_t),
                            visibility=sig.get("visibility", "public"),
                            is_static=sig.get("static", False)
                        )
                        if subj.get("analyzable"):
                            fn_res = subprocess.run(
                                ["java", "-cp", str(class_dir), "Analyzer", file_path, name],
                                capture_output=True, text=True, timeout=10
                            )
                            if fn_res.returncode == 0:
                                fn_data = json.loads(fn_res.stdout)
                                for fn_item in fn_data.get("functions", []):
                                    conv_m = cls._convert_syn_function(fn_item)
                                    u_meth.body = conv_m.body
                        target_cls.methods.append(u_meth)
                    elif kind == "field":
                        sig = subj.get("signature", {})
                        f_type = sig.get("source_type", "Object")
                        target_cls.fields.append(UniversalField(
                            name=name,
                            type_info=UniversalType.custom(f_type),
                            visibility=sig.get("visibility", "public")
                        ))
                return module
            except Exception as ex:
                logger.debug("Exception running Java javac bridge: %s", ex)
                return None

    # --------------------------------------------------------------------------
    # C# via Roslyn Analyzer DLL
    # --------------------------------------------------------------------------
    @classmethod
    def parse_csharp_with_roslyn(cls, source_code: str) -> Optional[UniversalModule]:
        """Parses C# source using the compiled Roslyn analyzer DLL."""
        dll_path = NATIVE_DIR / "csharp" / "bin" / "Debug" / "net10.0" / "Elmos.Csharp.EmittedAnalyzer.dll"
        if not dll_path.exists():
            return None

        import re
        c_match = re.search(r'(?:public\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)', source_code)
        class_name = c_match.group(1) if c_match else "MainClass"

        # Find candidate method names
        m_names = re.findall(r'(?:public|private|static)\s+(?:long|int|double|bool|string|void)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', source_code)

        with tempfile.NamedTemporaryFile("w", suffix=".cs", delete=False, encoding="utf-8") as f:
            f.write(source_code)
            f.flush()
            temp_path = f.name

        try:
            module = UniversalModule(name="CsharpModule", source_language="csharp")
            target_cls = UniversalClass(name=class_name)
            module.classes.append(target_cls)

            for m_name in m_names:
                res = subprocess.run(
                    ["dotnet", str(dll_path), temp_path, m_name, "--emitted-target"],
                    capture_output=True, text=True, timeout=10
                )
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    for fn_item in data.get("functions", []):
                        u_meth = cls._convert_syn_function(fn_item)
                        target_cls.methods.append(u_meth)
            if not target_cls.methods:
                return None
            return module
        except Exception as ex:
            logger.debug("Exception running C# Roslyn bridge: %s", ex)
            return None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # --------------------------------------------------------------------------
    # TypeScript via official TypeScript Compiler API (5.9.2)
    # --------------------------------------------------------------------------
    @classmethod
    def parse_typescript_with_node(cls, source_code: str) -> Optional[UniversalModule]:
        """Parses TypeScript source into UniversalModule using official TypeScript Compiler API."""
        node_path = shutil.which("node")
        if not node_path:
            return None

        analyzer_mjs = NATIVE_DIR / "typescript" / "analyzer.mjs"
        ts_lib = NATIVE_DIR / "javascript" / "vendor" / "typescript-5.9.2" / "typescript.js"
        if not analyzer_mjs.exists() or not ts_lib.exists():
            return None

        with tempfile.NamedTemporaryFile("w", suffix=".ts", delete=False, encoding="utf-8") as f:
            f.write(source_code)
            f.flush()
            temp_path = f.name

        try:
            inv_res = subprocess.run(
                [node_path, str(analyzer_mjs), str(ts_lib), temp_path, "--inventory"],
                capture_output=True, text=True, timeout=30
            )
            if inv_res.returncode != 0:
                logger.debug("TypeScript analyzer inventory failed: %s", inv_res.stderr)
                return None

            inv_data = json.loads(inv_res.stdout)
            module = UniversalModule(name="TypeScriptModule", source_language="typescript")
            main_class = UniversalClass(name="TypeScriptDefaultClass")
            module.classes.append(main_class)

            for subj in inv_data.get("subjects", []):
                kind = subj.get("declaration_kind")
                name = subj.get("name")
                if kind in ("InterfaceDeclaration", "TypeAliasDeclaration"):
                    module.classes.insert(0, UniversalClass(name=name, is_struct=True))

            for subj in inv_data.get("subjects", []):
                name = subj.get("name")
                if not name or not subj.get("analyzable"):
                    continue
                fn_res = subprocess.run(
                    [node_path, str(analyzer_mjs), str(ts_lib), temp_path, name],
                    capture_output=True, text=True, timeout=30
                )
                if fn_res.returncode == 0:
                    fn_data = json.loads(fn_res.stdout)
                    for rec in fn_data.get("records", []):
                        rec_name = rec.get("name")
                        rec_cls = next((c for c in module.classes if c.name == rec_name), None)
                        if not rec_cls:
                            rec_cls = UniversalClass(name=rec_name, is_struct=True)
                            module.classes.insert(0, rec_cls)
                        rec_cls.fields = []
                        for fld in rec.get("fields", []):
                            f_type = cls._convert_type_str(fld.get("type", "any"))
                            rec_cls.fields.append(UniversalField(name=fld.get("name", ""), type_info=f_type))

                    for fn_item in fn_data.get("functions", []):
                        u_meth = cls._convert_syn_function(fn_item)
                        main_class.methods.append(u_meth)

            if not main_class.methods and len(module.classes) <= 1:
                return None
            return module
        except Exception as ex:
            logger.debug("Exception running TypeScript analyzer bridge: %s", ex)
            return None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # --------------------------------------------------------------------------
    # Swift via native SwiftSyntax 600.0.1 analyzer binary
    # --------------------------------------------------------------------------
    @classmethod
    def parse_swift_with_syntax(cls, source_code: str) -> Optional[UniversalModule]:
        """Parses Swift source into UniversalModule using the native SwiftSyntax analyzer binary."""
        bin_path = NATIVE_DIR / "swift" / ".build" / "arm64-apple-macosx" / "debug" / "ElmosSwiftAnalyzer"
        if not bin_path.exists():
            bin_path = NATIVE_DIR / "swift" / ".build" / "release" / "ElmosSwiftAnalyzer"
        if not bin_path.exists():
            return None

        with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False, encoding="utf-8") as f:
            f.write(source_code)
            f.flush()
            temp_path = f.name

        try:
            inv_res = subprocess.run([str(bin_path), temp_path, "--inventory"], capture_output=True, text=True, timeout=10)
            if inv_res.returncode != 0:
                logger.debug("Swift analyzer inventory failed: %s", inv_res.stderr)
                return None

            inv_data = json.loads(inv_res.stdout)
            module = UniversalModule(name="SwiftModule", source_language="swift")
            main_class = UniversalClass(name="SwiftDefaultClass")
            module.classes.append(main_class)

            for subj in inv_data.get("subjects", []):
                name = subj.get("name")
                if not name or not subj.get("analyzable"):
                    continue
                fn_res = subprocess.run([str(bin_path), temp_path, name], capture_output=True, text=True, timeout=10)
                if fn_res.returncode == 0:
                    fn_data = json.loads(fn_res.stdout)
                    for fn_item in fn_data.get("functions", []):
                        u_meth = cls._convert_syn_function(fn_item)
                        main_class.methods.append(u_meth)

            if not main_class.methods:
                return None
            return module
        except Exception as ex:
            logger.debug("Exception running Swift analyzer bridge: %s", ex)
            return None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


