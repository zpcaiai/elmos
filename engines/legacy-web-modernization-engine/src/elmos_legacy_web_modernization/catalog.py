"""Pinned source-package catalog and dependency validation.

The source package is data.  This module parses YAML/Markdown metadata only;
it never imports, evaluates or executes anything from the package.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - small fallback keeps the CLI dependency-free
    yaml = None

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:  # pragma: no cover - optional for the local no-dependency CLI
    Draft202012Validator = None


EXPECTED_SKILLS = 55
PACKAGE_NAME = "elmos.java-legacy-web.repository-modernization"
PACKAGE_VERSION = "1.0.0"
PACKAGE_DIRECTORY = "elmos-legacy-web-repository-modernization-skills-v1.0.0"
EXPECTED_ARCHIVE_SHA256 = "45177c658f83b1d391f3b15ac913f0abeae39d0fa0611ea5eacb644be7a2f255"
EXPECTED_PHASES = (
    "control-plane",
    "repository-forensics",
    "semantic-recovery",
    "semantic-model",
    "planning",
    "transformation",
    "verification",
    "repair-certification",
)


@dataclass(frozen=True, slots=True)
class SkillSpec:
    skill_id: str
    title: str
    phase: str
    priority: str
    path: str
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    source_digest: str


@dataclass(frozen=True, slots=True)
class PackageCatalog:
    root: Path
    package_name: str
    version: str
    archive_digest: str
    manifest_digest: str
    skills: tuple[SkillSpec, ...]
    topological_order: tuple[str, ...]

    @property
    def skill_ids(self) -> tuple[str, ...]:
        return tuple(item.skill_id for item in self.skills)

    @property
    def by_id(self) -> dict[str, SkillSpec]:
        return {item.skill_id: item for item in self.skills}

    @classmethod
    def load(cls, repository_root: str | Path) -> "PackageCatalog":
        repository_root = Path(repository_root)
        root = repository_root / "skills" / PACKAGE_DIRECTORY
        archive = repository_root / "skills" / "subskills" / f"{PACKAGE_DIRECTORY}.zip"
        if not root.is_dir() or not archive.is_file():
            raise ValueError("legacy-web source package is missing")
        archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if archive_digest != EXPECTED_ARCHIVE_SHA256:
            raise ValueError("legacy-web source archive digest does not match the pinned input")
        package_text = (root / "package.yaml").read_text(encoding="utf-8")
        package = yaml.safe_load(package_text) if yaml is not None else _minimal_package_catalog(package_text)
        if not isinstance(package, dict) or package.get("id") != PACKAGE_NAME or package.get("version") != PACKAGE_VERSION:
            raise ValueError("legacy-web package identity is not exact")
        rows = package.get("skills")
        if not isinstance(rows, list) or len(rows) != EXPECTED_SKILLS:
            raise ValueError(f"legacy-web package must declare exactly {EXPECTED_SKILLS} skills")
        skills: list[SkillSpec] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("skill catalog row must be an object")
            skill_id = row.get("id")
            path = row.get("path")
            if not isinstance(skill_id, str) or not re.fullmatch(r"[0-9]{2}-[a-z0-9-]+", skill_id):
                raise ValueError("skill id is not exact")
            if skill_id in seen:
                raise ValueError(f"duplicate skill id: {skill_id}")
            seen.add(skill_id)
            if not isinstance(path, str) or not path.startswith("skills/") or ".." in Path(path).parts:
                raise ValueError(f"unsafe skill path: {path!r}")
            skill_file = root / path
            if not skill_file.is_file() or skill_file.is_symlink():
                raise ValueError(f"skill source is missing or unsafe: {path}")
            source = skill_file.read_text(encoding="utf-8")
            frontmatter = _frontmatter(source)
            if frontmatter.get("id") != skill_id:
                raise ValueError(f"skill source id does not match catalog: {skill_id}")
            skills.append(SkillSpec(
                skill_id=skill_id,
                title=str(row.get("title", frontmatter.get("title", skill_id))),
                phase=str(row.get("phase", "")),
                priority=str(row.get("priority", "")),
                path=path,
                requires=tuple(row.get("requires", ())),
                produces=tuple(row.get("produces", ())),
                source_digest="sha256:" + hashlib.sha256(skill_file.read_bytes()).hexdigest(),
            ))
        ids = set(seen)
        for spec in skills:
            missing = set(spec.requires) - ids
            if missing:
                raise ValueError(f"{spec.skill_id} requires missing skill(s): {sorted(missing)}")
        order_path = root / "build" / "skill-topological-order.txt"
        order = tuple(line.strip() for line in order_path.read_text(encoding="utf-8").splitlines() if line.strip())
        if set(order) != ids or len(order) != len(ids):
            raise ValueError("pinned topological order does not cover the exact skill catalog")
        positions = {skill_id: index for index, skill_id in enumerate(order)}
        for spec in skills:
            if any(positions[dependency] >= positions[spec.skill_id] for dependency in spec.requires):
                raise ValueError(f"topological order violates dependency of {spec.skill_id}")
        manifest_bytes = (root / "MANIFEST.sha256").read_bytes()
        manifest_digest = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
        _validate_manifest(root, manifest_bytes)
        return cls(
            root=root,
            package_name=PACKAGE_NAME,
            version=PACKAGE_VERSION,
            archive_digest="sha256:" + archive_digest,
            manifest_digest=manifest_digest,
            skills=tuple(skills),
            topological_order=order,
        )


def _frontmatter(source: str) -> dict[str, str]:
    if not source.startswith("---\n"):
        raise ValueError("skill source is missing front matter")
    end = source.find("\n---\n", 4)
    if end < 0:
        raise ValueError("skill source front matter is unterminated")
    value: dict[str, str] = {}
    for line in source[4:end].splitlines():
        if ":" in line:
            key, item = line.split(":", 1)
            value[key.strip()] = item.strip().strip("'\"")
    return value


def _minimal_package_catalog(source: str) -> dict[str, Any]:
    """Parse the pinned catalog subset without treating YAML as executable.

    PyYAML is used when available. This fallback is intentionally limited to
    the scalar/list fields in package.yaml and is not a general YAML parser.
    """

    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    list_field: str | None = None
    for line in source.splitlines():
        if line.startswith("- id: "):
            if current is not None:
                rows.append(current)
            current = {"id": line[6:].strip().strip("'\"")}
            list_field = None
            continue
        if current is None:
            continue
        scalar = re.match(r"^  (title|phase|priority|path):\s*(.*)$", line)
        if scalar:
            current[scalar.group(1)] = scalar.group(2).strip().strip("'\"")
            list_field = None
            continue
        list_start = re.match(r"^  (requires|produces):\s*(.*)$", line)
        if list_start:
            list_field = list_start.group(1)
            inline = list_start.group(2).strip()
            current[list_field] = [] if inline in {"", "[]"} else [inline.strip("[] '\"")]
            continue
        item = re.match(r"^  - (.+)$", line)
        if item and list_field:
            current.setdefault(list_field, []).append(item.group(1).strip().strip("'\""))
    if current is not None:
        rows.append(current)
    return {"id": PACKAGE_NAME, "version": PACKAGE_VERSION, "skills": rows}


def _validate_manifest(root: Path, manifest_bytes: bytes) -> None:
    expected: dict[str, str] = {}
    for line in manifest_bytes.decode("utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ValueError("malformed package manifest row")
        relative = parts[1].removeprefix("./")
        if not relative or relative.startswith("/") or ".." in Path(relative).parts:
            raise ValueError("unsafe package manifest path")
        expected[relative] = parts[0]
    actual: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError("package source contains unsafe non-regular file")
        relative = path.relative_to(root).as_posix()
        if relative == "MANIFEST.sha256":
            continue
        actual[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected != actual:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(path for path in set(expected) & set(actual) if expected[path] != actual[path])
        raise ValueError(f"package manifest mismatch missing={missing[:3]} extra={extra[:3]} changed={changed[:3]}")


_ARTIFACT_SCHEMA_NAMES = {
    "repository-evidence-graph": "repository-evidence-graph.schema.json",
    "legacy-web-semantic-ir": "legacy-web-semantic-ir.schema.json",
    "behavior-contract": "behavior-contract.schema.json",
    "unknown-semantics-ledger": "unknown-semantics-ledger.schema.json",
    "certification-bundle": "certification-bundle.schema.json",
    "equivalence-report": "equivalence-report.schema.json",
    "semantic-source-map": "semantic-source-map.schema.json",
    "wall-clock-estimate": "wall-clock-estimate.schema.json",
    "migration-plan": "migration-plan.schema.json",
}


def validate_artifact_payload(root: Path, artifact_type: str, payload: Mapping[str, Any]) -> None:
    """Validate package-defined artifacts at publish time when jsonschema exists."""

    if Draft202012Validator is None or artifact_type not in _ARTIFACT_SCHEMA_NAMES:
        return
    schema_path = root / "schemas" / _ARTIFACT_SCHEMA_NAMES[artifact_type]
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8")) if schema_path.suffix in {".yaml", ".yml"} else __import__("json").loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(dict(payload))
