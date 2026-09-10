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
                "!=": BinaryOperator.NEQ,
                "<": BinaryOperator.LT,
                "<=": BinaryOperator.LTE,
                ">": BinaryOperator.GT,
                ">=": BinaryOperator.GTE,
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
                    module.classes.append(UniversalClass(name=name, is_struct=True))
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
    def _convert_syn_function(cls, fn_dict: dict[str, Any]) -> UniversalMethod:
        f_name = fn_dict.get("name", "")
        params = []
        for p in fn_dict.get("parameters", []):
            pt = UniversalType.int64() if p.get("type") == "integer" else UniversalType.custom(p.get("type", "any"))
            params.append(UniversalParam(name=p.get("name", ""), type_info=pt))
        ret_t = UniversalType.int64() if fn_dict.get("return_type") == "integer" else UniversalType.custom(fn_dict.get("return_type", "void"))

        body = []
        for s in fn_dict.get("body", []):
            if s.get("kind") == "return":
                expr = cls._convert_syn_expr(s.get("expression", {}))
                body.append(ReturnStmt(value=expr))
        return UniversalMethod(name=f_name, params=params, return_type=ret_t, body=body)

    @classmethod
    def _convert_syn_expr(cls, expr_dict: dict[str, Any]) -> Optional[UniversalExpr]:
        kind = expr_dict.get("kind")
        if kind == "name":
            return IdentifierExpr(name=expr_dict.get("value", ""))
        if kind == "literal":
            val = expr_dict.get("value")
            t_kind = "int" if isinstance(val, int) else ("float" if isinstance(val, float) else "string")
            return LiteralExpr(value=val, type_kind=t_kind)
        if kind == "binary":
            op_str = expr_dict.get("operator", "+")
            left = cls._convert_syn_expr(expr_dict.get("left", {}))
            right = cls._convert_syn_expr(expr_dict.get("right", {}))
            op = BinaryOperator.ADD
            if op_str == "-":
                op = BinaryOperator.SUB
            elif op_str == "*":
                op = BinaryOperator.MUL
            elif op_str == "/":
                op = BinaryOperator.DIV
            if left and right:
                return BinaryExpr(left=left, op=op, right=right)
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
                    module.classes.append(UniversalClass(name=name, is_struct=True))
                elif kind == "function":
                    fn_res = subprocess.run([str(bin_path), temp_path, name], capture_output=True, text=True, timeout=10)
                    if fn_res.returncode == 0:
                        fn_data = json.loads(fn_res.stdout)
                        for fn_item in fn_data.get("functions", []):
                            u_meth = cls._convert_syn_function(fn_item)
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
                    if kind == "method" and subj.get("analyzable"):
                        fn_res = subprocess.run(
                            ["java", "-cp", str(class_dir), "Analyzer", file_path, name],
                            capture_output=True, text=True, timeout=10
                        )
                        if fn_res.returncode == 0:
                            fn_data = json.loads(fn_res.stdout)
                            for fn_item in fn_data.get("functions", []):
                                u_meth = cls._convert_syn_function(fn_item)
                                target_cls.methods.append(u_meth)
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
            return module
        except Exception as ex:
            logger.debug("Exception running C# Roslyn bridge: %s", ex)
            return None
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

