"""Explicit loader and validator for the immutable runtime Skill registry."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .canonical import canonical_digest
from .models import SkillKind


class RegistryError(ValueError):
    """Raised when the checked-in runtime registry is incomplete or inconsistent."""


ROOT_SKILL_NAME = "elmos-7plus1-commercial-software-factory"
EXPECTED_PACKAGE_IDS = frozenset(f"P{number:02d}" for number in range(8))
EXPECTED_CHILD_COUNT = 93
EXPECTED_BINDING_COUNT = 102
SUPPORTED_OPERATIONS = frozenset(
    {
        "root-route",
        "workflow",
        "runtime-plan",
        "repository-intelligence",
        "transformation-plan",
        "orchestration",
        "evidence-gate",
        "model-route",
        "knowledge",
    }
)


@dataclass(frozen=True)
class SkillBinding:
    name: str
    package_id: str
    kind: SkillKind
    operation: str
    dependencies: tuple[str, ...]
    adapter_actions: frozenset[str]


@dataclass(frozen=True)
class PackageDefinition:
    package_id: str
    name: str
    dependencies: tuple[str, ...]
    operation: str
    adapter_actions: frozenset[str]
    child_skills: tuple[str, ...]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise RegistryError(f"registry JSON contains duplicate key {key!r}")
        document[key] = value
    return document


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise RegistryError(f"{field} must be a non-empty bounded string")
    return value


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RegistryError(f"{field} must be an array")
    result = tuple(_string(item, f"{field}[]") for item in value)
    if len(set(result)) != len(result):
        raise RegistryError(f"{field} contains duplicates")
    return result


class SkillRegistry:
    def __init__(
        self,
        *,
        packages: Iterable[PackageDefinition],
        bindings: Mapping[str, SkillBinding],
        registry_digest: str,
    ) -> None:
        package_map = {item.package_id: item for item in packages}
        self._packages = MappingProxyType(package_map)
        self._bindings = MappingProxyType(dict(bindings))
        self.registry_digest = registry_digest
        self.validate()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "SkillRegistry":
        registry_path = Path(path) if path is not None else Path(__file__).with_name("skill_registry.json")
        try:
            raw = registry_path.read_text(encoding="utf-8")
            document = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RegistryError(f"cannot load registry {registry_path}: {exc}") from exc
        if not isinstance(document, Mapping):
            raise RegistryError("registry root must be an object")
        if set(document) != {"schema_version", "root_skill", "packages"}:
            raise RegistryError("registry root fields do not match schema 1.0")
        if document.get("schema_version") != "1.0":
            raise RegistryError("unsupported registry schema version")
        root = document.get("root_skill")
        if not isinstance(root, Mapping) or set(root) != {"name", "operation"}:
            raise RegistryError("root_skill must contain exact name and operation fields")
        root_name = _string(root.get("name"), "root_skill.name")
        root_operation = _string(root.get("operation"), "root_skill.operation")
        if root_name != ROOT_SKILL_NAME or root_operation != "root-route":
            raise RegistryError("repository root Skill identity is not the fixed runtime identity")

        package_documents = document.get("packages")
        if not isinstance(package_documents, list):
            raise RegistryError("packages must be an array")
        packages: list[PackageDefinition] = []
        bindings: dict[str, SkillBinding] = {
            root_name: SkillBinding(
                name=root_name,
                package_id="ROOT",
                kind=SkillKind.ROOT,
                operation=root_operation,
                dependencies=(),
                adapter_actions=frozenset(),
            )
        }
        for index, value in enumerate(package_documents):
            if not isinstance(value, Mapping):
                raise RegistryError(f"packages[{index}] must be an object")
            expected_fields = {
                "package_id",
                "name",
                "dependencies",
                "operation",
                "adapter_actions",
                "skills",
            }
            if set(value) != expected_fields:
                raise RegistryError(f"packages[{index}] fields do not match the registry schema")
            package_id = _string(value.get("package_id"), f"packages[{index}].package_id")
            name = _string(value.get("name"), f"packages[{index}].name")
            dependencies = _strings(value.get("dependencies"), f"packages[{index}].dependencies")
            operation = _string(value.get("operation"), f"packages[{index}].operation")
            adapter_action_values = _strings(
                value.get("adapter_actions"), f"packages[{index}].adapter_actions"
            )
            if adapter_action_values != tuple(sorted(adapter_action_values)):
                raise RegistryError(f"packages[{index}].adapter_actions must be sorted")
            adapter_actions = frozenset(adapter_action_values)
            children = _strings(value.get("skills"), f"packages[{index}].skills")
            if operation not in SUPPORTED_OPERATIONS - {"root-route"}:
                raise RegistryError(f"package {package_id} uses unsupported operation {operation}")
            package = PackageDefinition(
                package_id=package_id,
                name=name,
                dependencies=dependencies,
                operation=operation,
                adapter_actions=adapter_actions,
                child_skills=children,
            )
            packages.append(package)
            for skill_name, kind in ((name, SkillKind.PACKAGE), *((child, SkillKind.CHILD) for child in children)):
                if skill_name in bindings:
                    raise RegistryError(f"duplicate Skill binding {skill_name}")
                bindings[skill_name] = SkillBinding(
                    name=skill_name,
                    package_id=package_id,
                    kind=kind,
                    operation=operation,
                    dependencies=dependencies,
                    adapter_actions=adapter_actions,
                )
        return cls(
            packages=packages,
            bindings=bindings,
            registry_digest=canonical_digest(document),
        )

    @property
    def packages(self) -> Mapping[str, PackageDefinition]:
        return self._packages

    @property
    def bindings(self) -> Mapping[str, SkillBinding]:
        return self._bindings

    def binding(self, name: str) -> SkillBinding | None:
        return self._bindings.get(name)

    def validate(self) -> None:
        if set(self._packages) != EXPECTED_PACKAGE_IDS:
            raise RegistryError("registry must contain exactly P00 through P07")
        child_count = sum(len(item.child_skills) for item in self._packages.values())
        if child_count != EXPECTED_CHILD_COUNT or len(self._bindings) != EXPECTED_BINDING_COUNT:
            raise RegistryError("registry must bind one root, eight packages, and 93 child Skills")
        if any(not name.startswith("elmos-") for name in self._bindings):
            raise RegistryError("every runtime Skill binding must preserve its exact elmos-* identity")
        for package in self._packages.values():
            missing = sorted(set(package.dependencies) - set(self._packages))
            if missing:
                raise RegistryError(
                    f"package {package.package_id} has unknown dependencies: {', '.join(missing)}"
                )
            if package.package_id in package.dependencies:
                raise RegistryError(f"package {package.package_id} depends on itself")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(package_id: str) -> None:
            if package_id in visiting:
                raise RegistryError("package dependency graph contains a cycle")
            if package_id in visited:
                return
            visiting.add(package_id)
            for dependency in self._packages[package_id].dependencies:
                visit(dependency)
            visiting.remove(package_id)
            visited.add(package_id)

        for package_id in sorted(self._packages):
            visit(package_id)


def load_registry(path: str | Path | None = None) -> SkillRegistry:
    return SkillRegistry.load(path)


DEFAULT_SKILL_REGISTRY = load_registry()
SKILL_REGISTRY_DIGEST = DEFAULT_SKILL_REGISTRY.registry_digest
