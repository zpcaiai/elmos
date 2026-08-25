from __future__ import annotations

import platform
import re
import sysconfig
from hashlib import sha256
from pathlib import Path

from .domain import Distribution, EnvironmentSnapshot, ProjectInventory, ReproducibilityStatus


class EnvironmentReproducer:
    LOCK_NAMES = {"uv.lock", "pylock.toml", "poetry.lock", "Pipfile.lock", "conda-lock.yml"}
    ADAPTERS = ("UV", "PIP", "POETRY", "CONDA")

    def analyze(self, root: Path, inventory: ProjectInventory) -> EnvironmentSnapshot:
        lock_files = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name in self.LOCK_NAMES and not path.is_symlink()
        )
        distributions = self._declared_distributions(root)
        unpinned = "UNPINNED_DEPENDENCIES" in inventory.findings
        direct_git = "DIRECT_GIT_DEPENDENCY" in inventory.findings
        if lock_files and all(item.artifact_hash for item in distributions):
            status = ReproducibilityStatus.DEPENDENCY_REPRODUCIBLE
        elif lock_files:
            status = ReproducibilityStatus.FUNCTIONALLY_REPRODUCIBLE
        elif unpinned or direct_git:
            status = ReproducibilityStatus.UNREPRODUCIBLE
        else:
            status = ReproducibilityStatus.PARTIALLY_REPRODUCIBLE
        findings = []
        if not lock_files:
            findings.append("PYTHON_LOCK_MISSING")
        if unpinned:
            findings.append("PYTHON_DECLARATION_UNPINNED")
        if inventory.system_dependencies:
            findings.append("PYTHON_NATIVE_OR_SYSTEM_DEPENDENCIES_PRESENT")
        return EnvironmentSnapshot(
            python_version=next(
                (item.value for item in inventory.python_versions if item.kind == "DEPLOYMENT_PYTHON"), "UNRESOLVED"
            ),
            implementation="CPYTHON_OR_UNRESOLVED",
            platform={"os": "DECLARED_OR_UNRESOLVED", "architecture": "DECLARED_OR_UNRESOLVED"},
            abi="UNRESOLVED_UNTIL_RUNNER_CAPTURE",
            distributions=distributions,
            lock_files=lock_files,
            native_libraries=inventory.system_dependencies,
            environment_keys=[],
            reproducibility_status=status,
            reproduction_definition="DEPENDENCY_AND_PLATFORM" if lock_files else "NOT_YET_REPRODUCED",
            findings=findings,
        )

    def capture_engine_runtime(self) -> EnvironmentSnapshot:
        return EnvironmentSnapshot(
            python_version=platform.python_version(),
            implementation=platform.python_implementation(),
            platform={"os": platform.system(), "architecture": platform.machine()},
            abi=sysconfig.get_config_var("SOABI") or "UNKNOWN",
            distributions=[],
            lock_files=["uv.lock"],
            native_libraries=[],
            environment_keys=[],
            reproducibility_status=ReproducibilityStatus.DEPENDENCY_REPRODUCIBLE,
            reproduction_definition="ENGINE_RUNTIME_ONLY",
            findings=[],
        )

    @staticmethod
    def reproduction_stages() -> list[str]:
        return [
            "CAPTURE_EXISTING_ENVIRONMENT",
            "REPRODUCE_WITHOUT_CHANGE",
            "NORMALIZE_DEPENDENCY_METADATA",
            "GENERATE_CANDIDATE_LOCK",
            "OFFLINE_REPRODUCTION",
            "TARGET_ENVIRONMENT_LOCK",
        ]

    @staticmethod
    def _declared_distributions(root: Path) -> list[Distribution]:
        distributions: dict[str, Distribution] = {}
        for path in root.rglob("requirements*.txt"):
            if path.is_symlink() or not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                match = re.match(r"([A-Za-z0-9_.-]+)==([^\s;]+)(?:\s*;\s*(.+))?", stripped)
                if not match:
                    continue
                digest = None
                hash_match = re.search(r"--hash=sha256:([0-9a-fA-F]{64})", stripped)
                if hash_match:
                    digest = "sha256:" + hash_match.group(1).lower()
                normalized = match.group(1).lower().replace("_", "-")
                distributions[normalized] = Distribution(
                    name=normalized,
                    version=match.group(2),
                    artifact_hash=digest,
                    marker=match.group(3),
                )
        return sorted(distributions.values(), key=lambda item: item.name)


def content_hash(value: bytes) -> str:
    return sha256(value).hexdigest()
