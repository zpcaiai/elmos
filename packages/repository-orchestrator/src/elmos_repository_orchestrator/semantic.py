"""Semantic discovery and exact activation for the ELMOS Skill catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .contracts import ContractError, sha256_payload
from .retrieval import HybridIndex, RetrievalQuery, SearchDocument, SourceAnchor


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    name: str
    title: str
    description: str
    dependencies: tuple[str, ...] = ()
    vector: tuple[float, ...] | None = None
    tags: tuple[str, ...] = ()

    @property
    def searchable_text(self) -> str:
        return " ".join((self.name, self.title, self.description, *self.tags))


@dataclass(frozen=True, slots=True)
class SkillRoutePlan:
    catalog_digest: str
    discovered: tuple[str, ...]
    activated: tuple[str, ...]
    dependencies: Mapping[str, tuple[str, ...]]
    evidence: tuple[Mapping[str, object], ...] = field(default_factory=tuple)


class SemanticSkillRouter:
    """Hybrid Skill router that never invents or name-derives an activation."""

    def __init__(self, skills: Sequence[SkillDescriptor], *, catalog_digest: str | None = None):
        if not skills:
            raise ContractError("empty_skill_catalog", "skill catalog must not be empty")
        self._skills = {skill.name: skill for skill in skills}
        if len(self._skills) != len(skills):
            raise ContractError("duplicate_skill", "skill names must be unique")
        unknown = sorted(
            dependency
            for skill in skills
            for dependency in skill.dependencies
            if dependency not in self._skills
        )
        if unknown:
            raise ContractError("unknown_skill_dependency", "unknown skill dependencies: " + ", ".join(unknown))
        self.catalog_digest = catalog_digest or sha256_payload(
            [
                {
                    "name": skill.name,
                    "title": skill.title,
                    "description": skill.description,
                    "dependencies": skill.dependencies,
                    "tags": skill.tags,
                }
                for skill in sorted(skills, key=lambda item: item.name)
            ]
        )
        self._index = HybridIndex()
        documents = []
        for skill in skills:
            digest = sha256_payload(skill.searchable_text)
            documents.append(
                SearchDocument(
                    document_id=skill.name,
                    tenant_id="elmos-system",
                    project_id="skill-catalog",
                    revision_id=self.catalog_digest,
                    content=skill.searchable_text,
                    anchor=SourceAnchor(uri=f"skill://{skill.name}", kind="skill", content_sha256=digest),
                    allowed_principals=frozenset({"skill-router"}),
                    vector=skill.vector,
                    metadata={"dependencies": skill.dependencies},
                )
            )
        self._index.upsert(documents)

    def _dependency_closure(self, names: Sequence[str]) -> tuple[str, ...]:
        selected: list[str] = []
        visiting: set[str] = set()
        complete: set[str] = set()

        def visit(name: str) -> None:
            if name in complete:
                return
            if name in visiting:
                raise ContractError("skill_dependency_cycle", f"dependency cycle includes {name}")
            visiting.add(name)
            for dependency in self._skills[name].dependencies:
                visit(dependency)
            visiting.remove(name)
            complete.add(name)
            selected.append(name)

        for name in names:
            visit(name)
        return tuple(selected)

    def route(
        self,
        query: str,
        *,
        query_vector: Sequence[float] | None = None,
        discovery_limit: int = 16,
        activation_limit: int = 8,
    ) -> SkillRoutePlan:
        if not 1 <= discovery_limit <= 16:
            raise ContractError("discovery_limit_exceeded", "discovery_limit must be between 1 and 16")
        if not 1 <= activation_limit <= 8:
            raise ContractError("activation_limit_exceeded", "activation_limit must be between 1 and 8")
        hits = self._index.search(
            RetrievalQuery(
                tenant_id="elmos-system",
                project_id="skill-catalog",
                revision_id=self.catalog_digest,
                principal_ids=frozenset({"skill-router"}),
                text=query,
                vector=None if query_vector is None else tuple(query_vector),
                top_k=discovery_limit,
            )
        )
        discovered = tuple(hit.document.document_id for hit in hits)
        requested: list[str] = []
        for name in discovered:
            candidate = self._dependency_closure((*requested, name))
            if len(candidate) > activation_limit:
                continue
            requested.append(name)
        activated = self._dependency_closure(requested)
        return SkillRoutePlan(
            catalog_digest=self.catalog_digest,
            discovered=discovered,
            activated=activated,
            dependencies={name: self._skills[name].dependencies for name in activated},
            evidence=tuple(hit.to_payload() for hit in hits),
        )
