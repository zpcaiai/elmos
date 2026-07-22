from __future__ import annotations

import json
import re
import tomllib
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .domain import ProjectInventory, ProjectPath, ProjectRoot, PythonVersionEvidence

MANIFESTS = {
    "pyproject.toml": "PYPROJECT",
    "setup.py": "SETUP_PY",
    "setup.cfg": "SETUP_CFG",
    "requirements.txt": "REQUIREMENTS",
    "constraints.txt": "REQUIREMENTS",
    "Pipfile": "PIPENV",
    "Pipfile.lock": "PIPENV",
    "poetry.lock": "POETRY",
    "uv.lock": "UV",
    "pylock.toml": "PYLOCK",
    "environment.yml": "CONDA",
    "conda-lock.yml": "CONDA",
}
IGNORED = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".tox", ".nox"}
SYSTEM_PACKAGES = {"libpq", "libxml2", "libjpeg", "openssl", "gdal", "ffmpeg", "cuda", "cudnn", "blas", "lapack"}


class SafePythonDiscovery:
    def __init__(self, max_files: int = 10_000, max_file_bytes: int = 2_000_000) -> None:
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes

    def discover(self, root: Path, workspace_ref: str) -> ProjectInventory:
        root = root.resolve(strict=True)
        files, excluded = self._files(root)
        manifests: dict[Path, list[str]] = {}
        python_files: list[Path] = []
        notebooks: list[str] = []
        findings: set[str] = set()
        managers: set[str] = set()
        frameworks: set[str] = set()
        entries: list[dict[str, str]] = []
        versions: list[PythonVersionEvidence] = []
        indexes: set[str] = set()
        systems: set[str] = set()

        for path in files:
            relative = path.relative_to(root).as_posix()
            if path.name in MANIFESTS or path.name.startswith("requirements-") and path.suffix == ".txt":
                manifests.setdefault(path.parent, []).append(relative)
                managers.add(MANIFESTS.get(path.name, "REQUIREMENTS"))
            if path.suffix == ".py":
                python_files.append(path)
                self._inspect_python(path, root, entries, frameworks, findings)
            elif path.suffix == ".ipynb":
                notebooks.append(relative)
                entries.append({"type": "NOTEBOOK", "path": relative})
                self._inspect_notebook(path, findings)
            self._inspect_version_source(path, root, versions)
            if path.name.startswith("requirements") or path.name in {"Pipfile", "pyproject.toml"}:
                text = self._read_text(path)
                self._inspect_dependencies(text, indexes, findings)
            if path.name.lower() in {"dockerfile", "environment.yml", "conda-lock.yml"} or path.suffix in {
                ".sh",
                ".yml",
                ".yaml",
            }:
                lower = self._read_text(path).lower()
                systems.update(package for package in SYSTEM_PACKAGES if package in lower)

        if not manifests and python_files:
            manifests[root] = []
        if not manifests:
            findings.add("PYTHON_PROJECT_NOT_FOUND")
        if len(manifests) > 1:
            findings.add("PYTHON_MULTIPLE_PROJECT_ROOTS")
        if len(managers) > 1:
            findings.add("MULTIPLE_DEPENDENCY_MANAGERS")
        if not versions:
            findings.add("PYTHON_VERSION_UNRESOLVED")
        elif len({item.value for item in versions}) > 1:
            findings.add("PYTHON_VERSION_CONFLICT")
        if systems:
            findings.add("SYSTEM_PACKAGE_REQUIRED")

        projects = []
        for project_root, project_manifests in sorted(manifests.items(), key=lambda item: str(item[0])):
            relative = "." if project_root == root else project_root.relative_to(root).as_posix()
            project_type, paths = self._classify(project_root, files)
            project_id = "python-" + sha256(relative.encode()).hexdigest()[:16]
            projects.append(
                ProjectRoot(
                    project_id=project_id,
                    relative_path=relative,
                    project_type=project_type,
                    manifests=sorted(project_manifests),
                    paths=paths,
                )
            )

        return ProjectInventory(
            workspace_ref=workspace_ref,
            projects=projects,
            python_versions=self._dedupe_versions(versions),
            entry_points=sorted(entries, key=lambda item: (item["type"], item["path"])),
            dependency_managers=sorted(managers),
            frameworks=sorted(frameworks),
            notebooks=sorted(notebooks),
            system_dependencies=sorted(systems),
            index_sources=sorted(indexes),
            findings=sorted(findings),
            excluded_paths=sorted(excluded),
        )

    def _files(self, root: Path) -> tuple[list[Path], list[str]]:
        files: list[Path] = []
        excluded: list[str] = []
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if any(part in IGNORED for part in relative.parts):
                continue
            if path.is_symlink():
                excluded.append(relative.as_posix() + ":SYMLINK")
                continue
            if not path.is_file():
                continue
            if path.stat().st_size > self.max_file_bytes:
                excluded.append(relative.as_posix() + ":TOO_LARGE")
                continue
            files.append(path)
            if len(files) > self.max_files:
                raise ValueError("PYTHON_SCAN_FILE_LIMIT_EXCEEDED")
        return files, excluded

    def _inspect_python(
        self,
        path: Path,
        root: Path,
        entries: list[dict[str, str]],
        frameworks: set[str],
        findings: set[str],
    ) -> None:
        relative = path.relative_to(root).as_posix()
        text = self._read_text(path)
        patterns = {
            "DJANGO": ("django", "manage.py", "DJANGO_SETTINGS_MODULE"),
            "FLASK": ("flask", "Flask("),
            "AIRFLOW": ("airflow", "DAG("),
            "CELERY": ("celery", "Celery("),
            "SPARK": ("pyspark", "SparkSession"),
            "TENSORFLOW": ("tensorflow", "tf."),
            "PYTORCH": ("torch", "nn.Module"),
            "SCIKIT_LEARN": ("sklearn",),
        }
        for framework, needles in patterns.items():
            if any(needle in text or needle == path.name for needle in needles):
                frameworks.add(framework)
        if path.name == "manage.py":
            entries.append({"type": "DJANGO_MANAGE", "path": relative})
        if path.name in {"wsgi.py", "asgi.py"}:
            entries.append({"type": path.stem.upper(), "path": relative})
        if "Celery(" in text:
            entries.append({"type": "CELERY_APP", "path": relative})
        if "DAG(" in text:
            entries.append({"type": "AIRFLOW_DAG", "path": relative})
        if "if __name__" in text and "__main__" in text:
            entries.append({"type": "MODULE_ENTRY", "path": relative})
        if re.search(r"(?m)^\s*(?:setattr\s*\(|sys\.modules\[|[\w.]+\.[A-Za-z_]\w*\s*=)", text):
            findings.add("DYNAMIC_OR_MONKEY_PATCH_USAGE")

    def _inspect_notebook(self, path: Path, findings: set[str]) -> None:
        try:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            counts = [
                cell.get("execution_count") for cell in notebook.get("cells", []) if cell.get("cell_type") == "code"
            ]
            executed = [count for count in counts if isinstance(count, int)]
            if executed != sorted(executed) or any(count is None for count in counts):
                findings.add("NOTEBOOK_HIDDEN_STATE")
            if any("password" in "".join(cell.get("source", [])).lower() for cell in notebook.get("cells", [])):
                findings.add("NOTEBOOK_SECRET_REVIEW_REQUIRED")
        except OSError, UnicodeError, json.JSONDecodeError:
            findings.add("NOTEBOOK_STATE_UNRESOLVED")

    def _inspect_version_source(self, path: Path, root: Path, versions: list[PythonVersionEvidence]) -> None:
        relative = path.relative_to(root).as_posix()
        text = self._read_text(path)
        if path.name == "pyproject.toml":
            try:
                value = tomllib.loads(text).get("project", {}).get("requires-python")
                if value:
                    versions.append(
                        PythonVersionEvidence(
                            kind="DECLARED_PYTHON", value=str(value), source=relative, confidence="HIGH"
                        )
                    )
            except tomllib.TOMLDecodeError:
                pass
        elif path.name in {".python-version", "runtime.txt"}:
            value = text.strip()
            if value:
                versions.append(
                    PythonVersionEvidence(kind="DEPLOYMENT_PYTHON", value=value, source=relative, confidence="HIGH")
                )
        elif path.name == ".tool-versions":
            match = re.search(r"(?m)^python\s+([^\s]+)", text)
            if match:
                versions.append(
                    PythonVersionEvidence(
                        kind="DECLARED_PYTHON", value=match.group(1), source=relative, confidence="HIGH"
                    )
                )
        elif path.name in {"setup.py", "setup.cfg"}:
            match = re.search(r"python_requires\s*[=:]\s*['\"]?([^'\"\n,]+)", text)
            if match:
                versions.append(
                    PythonVersionEvidence(
                        kind="DECLARED_PYTHON", value=match.group(1).strip(), source=relative, confidence="MEDIUM"
                    )
                )
        elif path.name.lower() == "dockerfile":
            match = re.search(r"(?mi)^FROM\s+python:(\d+\.\d+(?:\.\d+)?)", text)
            if match:
                versions.append(
                    PythonVersionEvidence(
                        kind="DEPLOYMENT_PYTHON", value=match.group(1), source=relative, confidence="HIGH"
                    )
                )
        elif path.name in {"tox.ini", "noxfile.py"} or ".github/workflows" in relative or path.name == ".gitlab-ci.yml":
            for match in re.finditer(r"(?:python(?:-version)?\s*[:=]\s*['\"]?|py)(3\.\d{1,2})", text, re.IGNORECASE):
                versions.append(
                    PythonVersionEvidence(
                        kind="TEST_PYTHON", value=match.group(1), source=relative, confidence="MEDIUM"
                    )
                )

    @staticmethod
    def _inspect_dependencies(text: str, indexes: set[str], findings: set[str]) -> None:
        for raw_url in re.findall(r"https?://[^\s'\"]+", text):
            indexes.add(SafePythonDiscovery._redact_url(raw_url.rstrip(",]")))
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith(("-e ", "--editable")):
                findings.add("EDITABLE_PRODUCTION_DEPENDENCY")
            if "git+" in stripped:
                findings.add("DIRECT_GIT_DEPENDENCY")
                if "@" not in stripped.removeprefix("git+"):
                    findings.add("UNPINNED_GIT_DEPENDENCY")
            if (
                "==" not in stripped
                and not stripped.startswith(("--", "-r", "-c", "["))
                and re.match(r"[A-Za-z0-9_.-]+", stripped)
            ):
                findings.add("UNPINNED_DEPENDENCIES")
            if stripped.startswith(("--extra-index-url", "--find-links")):
                findings.add("PRIVATE_INDEX_REQUIRED")

    @staticmethod
    def _redact_url(value: str) -> str:
        try:
            parts = urlsplit(value)
            host = parts.hostname or ""
            if parts.port:
                host += f":{parts.port}"
            return urlunsplit((parts.scheme, host, parts.path, parts.query, ""))
        except ValueError:
            return "REDACTED_INVALID_INDEX_URL"

    @staticmethod
    def _classify(project_root: Path, files: list[Path]) -> tuple[str, list[ProjectPath]]:
        local = [path for path in files if path == project_root or project_root in path.parents]
        local_names = {path.name for path in local}
        local_frameworks: set[str] = set()
        patterns = {
            "DJANGO": ("django", "manage.py", "DJANGO_SETTINGS_MODULE"),
            "FLASK": ("flask", "Flask("),
            "AIRFLOW": ("airflow", "DAG("),
            "CELERY": ("celery", "Celery("),
            "SPARK": ("pyspark", "SparkSession"),
            "TENSORFLOW": ("tensorflow", "tf."),
            "PYTORCH": ("torch", "nn.Module"),
            "SCIKIT_LEARN": ("sklearn",),
        }
        for path in local:
            if path.suffix != ".py":
                continue
            text = SafePythonDiscovery._read_text(path)
            for framework, needles in patterns.items():
                if any(needle in text or needle == path.name for needle in needles):
                    local_frameworks.add(framework)
        paths: set[ProjectPath] = set()
        if local_frameworks.intersection({"DJANGO", "FLASK"}):
            paths.add(ProjectPath.WEB)
        if local_frameworks.intersection({"AIRFLOW", "CELERY", "SPARK"}) or any(
            path.suffix == ".ipynb" for path in local
        ):
            paths.add(ProjectPath.DATA_PIPELINE)
        if local_frameworks.intersection({"TENSORFLOW", "PYTORCH", "SCIKIT_LEARN"}):
            paths.add(ProjectPath.AI_ML)
        if not paths:
            paths.add(ProjectPath.GENERAL)
        manifest_names = local_names.intersection(MANIFESTS)
        if (
            not manifest_names
            and any(path.suffix == ".ipynb" for path in local)
            and not any(path.suffix == ".py" for path in local)
        ):
            kind = "NOTEBOOK_COLLECTION"
        elif not manifest_names and any(path.suffix == ".py" for path in local):
            kind = "SCRIPT_COLLECTION"
        elif "uv.lock" in local_names:
            kind = "UV_WORKSPACE" if "pyproject.toml" in local_names else "UV_PROJECT"
        elif "poetry.lock" in local_names:
            kind = "POETRY_PROJECT"
        elif "environment.yml" in local_names:
            kind = "CONDA_PROJECT"
        elif ProjectPath.WEB in paths:
            kind = "DJANGO_PROJECT" if "DJANGO" in local_frameworks else "FLASK_APPLICATION"
        elif ProjectPath.AI_ML in paths:
            kind = "ML_PROJECT"
        elif ProjectPath.DATA_PIPELINE in paths:
            kind = "DATA_PIPELINE"
        else:
            kind = "SINGLE_PACKAGE"
        return kind, sorted(paths, key=str)

    @staticmethod
    def _dedupe_versions(items: list[PythonVersionEvidence]) -> list[PythonVersionEvidence]:
        unique = {(item.kind, item.value, item.source): item for item in items}
        return sorted(unique.values(), key=lambda item: (item.kind, item.source, item.value))

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
