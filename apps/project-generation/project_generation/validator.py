"""DDD Architectural static constraint validator."""

import ast
import json
import os
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Layer(str, Enum):
    DOMAIN = "Domain"
    APPLICATION = "Application"
    INFRASTRUCTURE = "Infrastructure"
    INTERFACES = "Interfaces"
    PKG = "Pkg"
    COMPOSITION = "CompositionRoot"
    UNKNOWN = "Unknown"


@dataclass
class Violation:
    file: str
    line: int
    source_layer: str
    target_layer: str
    import_path: str
    rule: str
    message: str


@dataclass
class ValidationReport:
    valid: bool
    checked_files: int
    violations: List[Violation] = field(default_factory=list)
    summary: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "valid": self.valid,
                "checked_files": self.checked_files,
                "violations": [asdict(v) for v in self.violations],
                "summary": self.summary,
            },
            indent=2,
        )

    def __str__(self) -> str:
        lines = [
            "=== DDD Architecture Compliance Report ===",
            f"Checked Files: {self.checked_files}",
            f"Violations Found: {len(self.violations)}",
            f"Status: {'PASSED (100% Compliant)' if self.valid else 'FAILED'}",
        ]
        if self.violations:
            lines.append("\nViolations List:")
            for i, v in enumerate(self.violations, 1):
                lines.append(f"  [{i}] {v.file}:{v.line}")
                lines.append(f"      Rule: {v.rule}")
                lines.append(f"      Violation: Layer '{v.source_layer}' illegally imports Layer '{v.target_layer}' via '{v.import_path}'")
                lines.append(f"      Detail: {v.message}")
        return "\n".join(lines)


class DDDValidator:
    """Static analysis engine for validating Domain-Driven Design layer constraints."""

    def validate(self, project_dir: str) -> ValidationReport:
        root_path = Path(project_dir).resolve()
        violations: List[Violation] = []
        checked_files = 0

        for root, dirs, files in os.walk(root_path):
            # Skip non-source directories
            dirs[:] = [d for d in dirs if d not in {".git", "vendor", ".venv", "node_modules", "__pycache__"}]

            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(root_path)

                if file.endswith(".py"):
                    checked_files += 1
                    file_violations = self._validate_python_file(root_path, rel_path, full_path)
                    violations.extend(file_violations)
                elif file.endswith(".go"):
                    checked_files += 1
                    file_violations = self._validate_go_file(root_path, rel_path, full_path)
                    violations.extend(file_violations)

        is_valid = len(violations) == 0
        summary = (
            f"All {checked_files} files strictly adhere to DDD architecture layer boundaries."
            if is_valid
            else f"Found {len(violations)} architectural violations across {checked_files} files."
        )

        return ValidationReport(
            valid=is_valid,
            checked_files=checked_files,
            violations=violations,
            summary=summary,
        )

    def _detect_layer(self, rel_path: Path) -> Layer:
        posix = rel_path.as_posix()
        # Composition Root
        if posix in ("app/main.py", "main.py", "cmd/server/main.go") or posix.startswith("cmd/"):
            return Layer.COMPOSITION
        if posix.startswith("tests/"):
            return Layer.COMPOSITION

        # Domain
        if "internal/domain/" in posix or posix.startswith("app/domain/"):
            return Layer.DOMAIN
        # Application
        if "internal/application/" in posix or posix.startswith("app/application/"):
            return Layer.APPLICATION
        # Infrastructure
        if "internal/infrastructure/" in posix or posix.startswith("app/infrastructure/"):
            return Layer.INFRASTRUCTURE
        # Interfaces
        if "internal/interfaces/" in posix or posix.startswith("app/interfaces/"):
            return Layer.INTERFACES
        # Pkg / Shared Utilities
        if posix.startswith("pkg/"):
            return Layer.PKG

        return Layer.UNKNOWN

    def _detect_import_layer(self, import_str: str) -> Layer:
        clean = import_str.replace(".", "/")
        # Explicit internal layer boundaries to prevent false positives from 3rd party packages
        # (e.g. 'fastapi.applications', 'google.cloud.application_default_credentials')
        if (
            clean.startswith("app/domain/")
            or clean == "app/domain"
            or "/internal/domain" in clean
            or clean.startswith("internal/domain")
        ):
            return Layer.DOMAIN
        if (
            clean.startswith("app/application/")
            or clean == "app/application"
            or "/internal/application" in clean
            or clean.startswith("internal/application")
        ):
            return Layer.APPLICATION
        if (
            clean.startswith("app/infrastructure/")
            or clean == "app/infrastructure"
            or "/internal/infrastructure" in clean
            or clean.startswith("internal/infrastructure")
        ):
            return Layer.INFRASTRUCTURE
        if (
            clean.startswith("app/interfaces/")
            or clean == "app/interfaces"
            or "/internal/interfaces" in clean
            or clean.startswith("internal/interfaces")
        ):
            return Layer.INTERFACES
        if clean.startswith("pkg/") or "/pkg" in clean or clean == "pkg":
            return Layer.PKG
        return Layer.UNKNOWN

    def _validate_python_file(self, root: Path, rel_path: Path, full_path: Path) -> List[Violation]:
        source_layer = self._detect_layer(rel_path)
        if source_layer in (Layer.COMPOSITION, Layer.UNKNOWN, Layer.PKG):
            return []

        violations: List[Violation] = []
        is_di_factory = "dependencies.py" in rel_path.name

        try:
            content = full_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(full_path))
        except Exception:
            return []

        for node in ast.walk(tree):
            import_path = ""
            lineno = getattr(node, "lineno", 1)

            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_path = alias.name
                    v = self._check_rule(rel_path, lineno, source_layer, import_path, is_di_factory)
                    if v:
                        violations.append(v)
            elif isinstance(node, ast.ImportFrom):
                raw_module = node.module or ""
                if node.level and node.level > 0:
                    # Resolve relative import to canonical package path
                    pkg_parts = list(rel_path.parent.parts)
                    if node.level <= len(pkg_parts):
                        base_parts = pkg_parts[: len(pkg_parts) - node.level + 1]
                        if raw_module:
                            base_parts.extend(raw_module.split("."))
                        import_path = ".".join(base_parts)
                    elif raw_module:
                        import_path = raw_module
                else:
                    import_path = raw_module

                if import_path:
                    v = self._check_rule(rel_path, lineno, source_layer, import_path, is_di_factory)
                    if v:
                        violations.append(v)
            elif isinstance(node, ast.Call):
                # Detect dynamic imports: importlib.import_module(...) or __import__(...) or import_module(...)
                is_dynamic_import = False
                if isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                    is_dynamic_import = True
                elif isinstance(node.func, ast.Name) and node.func.id in ("import_module", "__import__"):
                    is_dynamic_import = True

                if is_dynamic_import:
                    arg_node = None
                    if node.args:
                        arg_node = node.args[0]
                    elif node.keywords:
                        for kw in node.keywords:
                            if kw.arg in ("name", "module"):
                                arg_node = kw.value
                                break

                    target_paths: List[str] = []
                    if isinstance(arg_node, ast.Constant) and isinstance(arg_node.value, str):
                        target_paths.append(arg_node.value)
                    elif isinstance(arg_node, ast.JoinedStr):
                        parts = [
                            part.value
                            for part in arg_node.values
                            if isinstance(part, ast.Constant) and isinstance(part.value, str)
                        ]
                        if parts:
                            target_paths.append("".join(parts))

                    for target_path in target_paths:
                        v = self._check_rule(rel_path, lineno, source_layer, target_path, is_di_factory)
                        if v:
                            v.message += f" (detected dynamic reflection import: '{target_path}')"
                            violations.append(v)

        return violations

    def _validate_go_file(self, root: Path, rel_path: Path, full_path: Path) -> List[Violation]:
        source_layer = self._detect_layer(rel_path)
        if source_layer in (Layer.COMPOSITION, Layer.UNKNOWN, Layer.PKG):
            return []

        violations: List[Violation] = []
        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception:
            return []

        import_re = re.compile(r'^\s*(?:import\s+)?(?:\w+\s+)?"([^"]+)"')
        for lineno, line in enumerate(content.splitlines(), 1):
            m = import_re.match(line)
            if m:
                import_path = m.group(1)
                v = self._check_rule(rel_path, lineno, source_layer, import_path, False)
                if v:
                    violations.append(v)

        return violations

    def _check_rule(
        self,
        rel_path: Path,
        lineno: int,
        source_layer: Layer,
        import_path: str,
        is_di_factory: bool,
    ) -> Optional[Violation]:
        target_layer = self._detect_import_layer(import_path)
        if target_layer in (Layer.UNKNOWN, Layer.PKG):
            return None

        # Rule 1: Domain layer must NEVER depend on outer layers
        if source_layer == Layer.DOMAIN:
            if target_layer in (Layer.APPLICATION, Layer.INFRASTRUCTURE, Layer.INTERFACES):
                return Violation(
                    file=str(rel_path),
                    line=lineno,
                    source_layer=source_layer.value,
                    target_layer=target_layer.value,
                    import_path=import_path,
                    rule="Rule 1: Domain layer must not depend on Application, Infrastructure, or Interfaces",
                    message=f"Domain file '{rel_path}' violates isolation by importing {import_path}",
                )

        # Rule 2: Application layer can ONLY depend on Domain
        if source_layer == Layer.APPLICATION:
            if target_layer in (Layer.INFRASTRUCTURE, Layer.INTERFACES):
                return Violation(
                    file=str(rel_path),
                    line=lineno,
                    source_layer=source_layer.value,
                    target_layer=target_layer.value,
                    import_path=import_path,
                    rule="Rule 2: Application layer can only depend on Domain, never on Infrastructure or Interfaces",
                    message=f"Application file '{rel_path}' violates layer direction by importing {import_path}",
                )

        # Rule 3: Interfaces layer must not directly depend on Infrastructure (except composition DI factory)
        if source_layer == Layer.INTERFACES and not is_di_factory:
            if target_layer == Layer.INFRASTRUCTURE:
                return Violation(
                    file=str(rel_path),
                    line=lineno,
                    source_layer=source_layer.value,
                    target_layer=target_layer.value,
                    import_path=import_path,
                    rule="Rule 3: Interfaces must not directly depend on Infrastructure implementations",
                    message=f"Interfaces file '{rel_path}' directly couples with Infrastructure {import_path}",
                )

        return None
