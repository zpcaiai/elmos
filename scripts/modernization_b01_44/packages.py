#!/usr/bin/env python3
"""Load, verify and index the Batch 01-44 Skill packages.

Package content is *data*.  Nothing in a package is imported, evaluated or
executed; the loader reads bytes, verifies digests against the package manifest
and exposes typed views.  A package that does not verify is refused rather than
silently downgraded.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from scripts.modernization_b01_44.canonical import digest_bytes
from scripts.modernization_b01_44.errors import PackageError

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK_ROOT = ROOT / "skills" / "modernization-skills-batch-01-44"

BATCH_DIR_RE = re.compile(r"^batch_(\d{2})_(.+?)_complete_skill_pack$")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)

#: The sixteen archetypes every Batch package must provide.  These are the
#: units the runtime actually dispatches on, so the list is a hard contract.
SKILL_ARCHETYPES = (
    "orchestrator",
    "domain-model",
    "discovery-inventory",
    "capability-planning",
    "deterministic-engine",
    "adapter-provider",
    "integration-api",
    "workflow-runtime",
    "certification-gate",
    "security-policy",
    "human-approval",
    "failure-recovery",
    "lineage-reconciliation",
    "lifecycle-recertification",
    "observability-economics",
    "corpus-benchmark",
)

REQUIRED_SCHEMAS = (
    "batch-input",
    "batch-output",
    "capability-package",
    "certification",
    "evidence-ref",
    "workflow-run",
)

REQUIRED_POLICIES = (
    "agent-boundary",
    "certification",
    "default-deny",
    "evidence-first",
    "human-approval",
)

REQUIRED_SKILL_SECTIONS = (
    "## Objective",
    "## Workflow",
    "## Required Tests",
    "## Verification",
    "## Stop and Escalate",
    "## Definition of Done",
)


def _parse_frontmatter(text: str, source: Path) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise PackageError("SKILL.md is missing YAML frontmatter", path=str(source))
    parsed: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise PackageError("malformed frontmatter line", path=str(source), line=line)
        key, _, value = line.partition(":")
        parsed[key.strip()] = value.strip().strip('"')
    return parsed


@dataclass(frozen=True)
class Skill:
    """One installable Skill inside a Batch package."""

    name: str
    archetype: str
    batch: int
    version: str
    risk: str
    status: str
    description: str
    path: Path
    body: str

    def section(self, heading: str) -> str:
        """Return the body of a ``## Heading`` section, or '' when absent."""

        marker = f"\n{heading}\n"
        start = self.body.find(marker)
        if start < 0:
            return ""
        start += len(marker)
        nxt = self.body.find("\n## ", start)
        return self.body[start : nxt if nxt >= 0 else len(self.body)].strip()

    def bullets(self, heading: str) -> list[str]:
        return [
            line[2:].strip()
            for line in self.section(heading).splitlines()
            if line.startswith("- ")
        ]


@dataclass(frozen=True)
class TestCase:
    """A declared conformance obligation from ``tests/test_catalog.json``."""

    case_id: str
    name: str
    priority: str
    expected: str
    batch: int


@dataclass
class BatchPackage:
    """A verified Batch package: skills, schemas, policies and obligations."""

    batch: int
    slug: str
    path: Path
    skills: dict[str, Skill] = field(default_factory=dict)
    schemas: dict[str, dict[str, Any]] = field(default_factory=dict)
    policies: dict[str, dict[str, Any]] = field(default_factory=dict)
    test_cases: tuple[TestCase, ...] = ()
    manifest: dict[str, Any] = field(default_factory=dict)
    verified_files: int = 0
    problems: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.problems

    def skill(self, archetype: str) -> Skill:
        try:
            return self.skills[archetype]
        except KeyError:
            raise PackageError(
                "batch does not provide the requested archetype",
                batch=self.batch,
                archetype=archetype,
            ) from None

    def schema(self, name: str) -> dict[str, Any]:
        try:
            return self.schemas[name]
        except KeyError:
            raise PackageError("batch is missing a schema", batch=self.batch, schema=name) from None

    def policy(self, name: str) -> dict[str, Any]:
        try:
            return self.policies[name]
        except KeyError:
            raise PackageError("batch is missing a policy", batch=self.batch, policy=name) from None


def _load_yaml(path: Path) -> dict[str, Any]:
    """Parse the small, flat YAML dialect the policy files are written in.

    A dependency-free parser keeps the trust boundary narrow: only mappings of
    scalars and nested mappings are accepted, so a policy file cannot smuggle
    an object graph or a tag directive into the runtime.
    """

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            raise PackageError("unsupported policy syntax", path=str(path), line=lineno)
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            raise PackageError("policy indentation is inconsistent", path=str(path), line=lineno)
        parent = stack[-1][1]
        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
            continue
        if value in ("true", "false"):
            parent[key] = value == "true"
        elif re.fullmatch(r"-?\d+", value):
            parent[key] = int(value)
        else:
            parent[key] = value.strip('"')
    return root


def _verify_manifest(pkg_path: Path, problems: list[str]) -> tuple[dict[str, Any], int]:
    manifest_path = pkg_path / "PACKAGE_MANIFEST.json"
    if not manifest_path.is_file():
        problems.append("PACKAGE_MANIFEST.json is missing")
        return {}, 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified = 0
    for entry in manifest.get("files", []):
        target = pkg_path / entry["path"]
        if not target.is_file():
            problems.append(f"manifest file missing: {entry['path']}")
            continue
        actual = digest_bytes(target.read_bytes())
        if actual != entry["sha256"]:
            problems.append(f"digest mismatch: {entry['path']}")
            continue
        verified += 1
    return manifest, verified


def load_package(pkg_path: Path) -> BatchPackage:
    """Load and verify one Batch package directory."""

    match = BATCH_DIR_RE.match(pkg_path.name)
    if not match:
        raise PackageError("not a Batch package directory", path=str(pkg_path))
    batch = int(match.group(1))
    slug = match.group(2)
    problems: list[str] = []

    manifest, verified = _verify_manifest(pkg_path, problems)

    # Two package layouts are supported.  Batch 06-44 name each Skill
    # ``b<NN>-<slug>-<archetype>`` so the archetype is implicit.  Batch 01-05
    # ship bespoke Skill names plus an explicit ``ARCHETYPE_MAP.json``.
    archetype_map: dict[str, str] = {}
    map_path = pkg_path / "ARCHETYPE_MAP.json"
    if map_path.is_file():
        archetype_map = json.loads(map_path.read_text(encoding="utf-8")).get("archetypes", {})

    skills: dict[str, Skill] = {}
    by_name: dict[str, Skill] = {}
    skills_dir = pkg_path / "skills"
    if not skills_dir.is_dir():
        problems.append("skills/ directory is missing")
    else:
        prefix = f"b{batch:02d}-{slug}-"
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8")
            front = _parse_frontmatter(text, skill_md)
            name = front.get("name", "")
            if not name:
                problems.append(f"frontmatter name is empty: {skill_md.parent.name}")
                continue
            if not archetype_map and name != skill_md.parent.name:
                problems.append(f"frontmatter name != directory: {skill_md.parent.name}")
                continue
            for heading in REQUIRED_SKILL_SECTIONS:
                if heading not in text:
                    problems.append(f"{name} is missing section {heading}")
            skill = Skill(
                name=name,
                archetype=front.get("archetype", "") or (name[len(prefix) :] if name.startswith(prefix) else ""),
                batch=batch,
                version=front.get("version", ""),
                risk=front.get("risk", ""),
                status=front.get("status", ""),
                description=front.get("description", ""),
                path=skill_md,
                body=text,
            )
            by_name[name] = skill
            if not archetype_map:
                if not name.startswith(prefix):
                    problems.append(f"skill name does not carry the batch prefix: {name}")
                    continue
                skills[skill.archetype] = skill

        if archetype_map:
            for archetype, skill_name in archetype_map.items():
                target = by_name.get(skill_name)
                if target is None:
                    problems.append(f"archetype map points at an absent skill: {skill_name}")
                    continue
                skills[archetype] = target

        missing = [a for a in SKILL_ARCHETYPES if a not in skills]
        if missing:
            problems.append("missing archetypes: " + ",".join(missing))

    schemas: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_SCHEMAS:
        schema_path = pkg_path / "schemas" / f"{name}.schema.json"
        if not schema_path.is_file():
            problems.append(f"schema missing: {name}")
            continue
        try:
            schemas[name] = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"schema is not valid JSON: {name} ({exc})")

    policies: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_POLICIES:
        policy_path = pkg_path / "policies" / f"{name}.yaml"
        if not policy_path.is_file():
            problems.append(f"policy missing: {name}")
            continue
        policies[name] = _load_yaml(policy_path)

    cases: tuple[TestCase, ...] = ()
    catalog_path = pkg_path / "tests" / "test_catalog.json"
    if not catalog_path.is_file():
        problems.append("tests/test_catalog.json is missing")
    else:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        if catalog.get("batch") != batch:
            problems.append("test catalog declares the wrong batch")
        cases = tuple(
            TestCase(
                case_id=case["id"],
                name=case["name"],
                priority=case["priority"],
                expected=case["expected"],
                batch=batch,
            )
            for case in catalog.get("cases", [])
        )

    return BatchPackage(
        batch=batch,
        slug=slug,
        path=pkg_path,
        skills=skills,
        schemas=schemas,
        policies=policies,
        test_cases=cases,
        manifest=manifest,
        verified_files=verified,
        problems=tuple(problems),
    )


@dataclass(frozen=True)
class PackageRegistry:
    """All Batch packages, indexed by batch number."""

    root: Path
    packages: dict[int, BatchPackage]

    def __iter__(self) -> Iterator[BatchPackage]:
        for batch in sorted(self.packages):
            yield self.packages[batch]

    def __len__(self) -> int:
        return len(self.packages)

    def get(self, batch: int) -> BatchPackage:
        try:
            return self.packages[batch]
        except KeyError:
            raise PackageError("unknown batch", batch=batch) from None

    def upstream_of(self, batch: int) -> int | None:
        """The immediate upstream batch in the B01 -> B44 certification chain."""

        return batch - 1 if batch > 1 else None

    def complete_batches(self) -> list[int]:
        return [pkg.batch for pkg in self if pkg.complete]

    def incomplete_batches(self) -> dict[int, tuple[str, ...]]:
        return {pkg.batch: pkg.problems for pkg in self if not pkg.complete}


def load_registry(root: Path | None = None) -> PackageRegistry:
    base = Path(root) if root is not None else DEFAULT_PACK_ROOT
    if not base.is_dir():
        raise PackageError("skill pack root does not exist", path=str(base))
    packages: dict[int, BatchPackage] = {}
    for child in sorted(base.iterdir()):
        if not child.is_dir() or not BATCH_DIR_RE.match(child.name):
            continue
        pkg = load_package(child)
        if pkg.batch in packages:
            raise PackageError("duplicate batch directory", batch=pkg.batch)
        packages[pkg.batch] = pkg
    if not packages:
        raise PackageError("no Batch packages found", path=str(base))
    return PackageRegistry(root=base, packages=packages)


@lru_cache(maxsize=4)
def cached_registry(root: str | None = None) -> PackageRegistry:
    return load_registry(Path(root) if root else None)
