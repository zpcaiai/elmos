from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple


@dataclass
class ModuleNode:
    name: str
    relative_path: str
    pom_path: Path
    group_id: str = ""
    artifact_id: str = ""
    version: str = ""
    parent_artifact_id: Optional[str] = None
    internal_dependencies: Set[str] = field(default_factory=set)


@dataclass
class ModernizationWave:
    wave_index: int
    modules: List[str]
    description: str


@dataclass
class WaveExecutionPlan:
    root_dir: str
    total_modules: int
    waves: List[ModernizationWave]
    dependency_graph: Dict[str, List[str]]
    has_cycles: bool = False
    cycle_nodes: List[str] = field(default_factory=list)


@dataclass
class WaveCheckpoint:
    project_root: str
    completed_waves: List[int] = field(default_factory=list)
    completed_modules: Set[str] = field(default_factory=set)
    failed_modules: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "project_root": self.project_root,
            "completed_waves": self.completed_waves,
            "completed_modules": sorted(list(self.completed_modules)),
            "failed_modules": self.failed_modules,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WaveCheckpoint:
        return cls(
            project_root=data.get("project_root", ""),
            completed_waves=data.get("completed_waves", []),
            completed_modules=set(data.get("completed_modules", [])),
            failed_modules=data.get("failed_modules", {}),
        )


class MultiModuleWaveOrchestrator:
    """
    Industrial-grade Multi-Module Monorepo Wave Modernization Orchestrator.
    Discovers multi-module Maven repository structures, builds internal dependency DAGs,
    computes topological modernization waves (Domain/DTO -> DAL -> Service -> Web/App),
    and coordinates wave-by-wave execution with checkpointing and resume.
    """

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()

    def inspect_and_plan(self) -> WaveExecutionPlan:
        root_pom = self.project_root / "pom.xml"
        if not root_pom.is_file():
            # Not a maven root, return single standalone wave
            return WaveExecutionPlan(
                root_dir=str(self.project_root),
                total_modules=1,
                waves=[ModernizationWave(wave_index=0, modules=["."], description="Standalone single-module workspace")],
                dependency_graph={},
                has_cycles=False,
            )

        module_nodes = self._discover_modules(root_pom)
        if not module_nodes:
            return WaveExecutionPlan(
                root_dir=str(self.project_root),
                total_modules=1,
                waves=[ModernizationWave(wave_index=0, modules=["."], description="Single-module workspace")],
                dependency_graph={},
                has_cycles=False,
            )

        # Build internal dependency edges
        self._resolve_internal_dependencies(module_nodes)

        # Build dependency graph: dependency_graph[A] = list of modules that depend on A (or vice versa)
        # For wave topological execution: Module B depends on Module A means Module A must be upgraded before B.
        # So in-degree in prerequisite graph: prerequisites[B] = {A}
        prerequisites: Dict[str, Set[str]] = {m.name: set(m.internal_dependencies) for m in module_nodes.values()}
        dep_graph_repr: Dict[str, List[str]] = {k: sorted(list(v)) for k, v in prerequisites.items()}

        waves, has_cycles, cycle_nodes = self._compute_topological_waves(prerequisites)

        return WaveExecutionPlan(
            root_dir=str(self.project_root),
            total_modules=len(module_nodes),
            waves=waves,
            dependency_graph=dep_graph_repr,
            has_cycles=has_cycles,
            cycle_nodes=cycle_nodes,
        )

    def _discover_modules(self, root_pom: Path) -> Dict[str, ModuleNode]:
        modules: Dict[str, ModuleNode] = {}
        try:
            content = root_pom.read_text(encoding="utf-8")
            # Extract <modules><module>...</module></modules>
            module_names = re.findall(r"<module>([^<]+)</module>", content)
            if not module_names:
                return {}

            for mod_rel in module_names:
                mod_rel = mod_rel.strip()
                mod_dir = self.project_root / mod_rel
                mod_pom = mod_dir / "pom.xml"
                if mod_pom.is_file():
                    node = self._parse_module_pom(mod_rel, mod_pom)
                    modules[node.name] = node

        except Exception:
            pass

        return modules

    def _parse_module_pom(self, mod_rel: str, pom_path: Path) -> ModuleNode:
        node = ModuleNode(name=mod_rel, relative_path=mod_rel, pom_path=pom_path)
        try:
            content = pom_path.read_text(encoding="utf-8")
            # Basic tag extraction
            art_match = re.search(r"<artifactId>([^<]+)</artifactId>", content)
            if art_match:
                node.artifact_id = art_match.group(1).strip()

            grp_match = re.search(r"<groupId>([^<]+)</groupId>", content)
            if grp_match:
                node.group_id = grp_match.group(1).strip()

            ver_match = re.search(r"<version>([^<]+)</version>", content)
            if ver_match:
                node.version = ver_match.group(1).strip()

            # Parent artifactId
            parent_match = re.search(r"<parent>.*?<artifactId>([^<]+)</artifactId>.*?</parent>", content, re.DOTALL)
            if parent_match:
                node.parent_artifact_id = parent_match.group(1).strip()

        except Exception:
            pass

        return node

    def _resolve_internal_dependencies(self, modules: Dict[str, ModuleNode]) -> None:
        # Create map of artifactId -> module_name
        artifact_to_name: Dict[str, str] = {}
        for name, mod in modules.items():
            if mod.artifact_id:
                artifact_to_name[mod.artifact_id] = name
            artifact_to_name[name] = name

        for name, mod in modules.items():
            try:
                content = mod.pom_path.read_text(encoding="utf-8")
                # Look for all <dependency> artifactIds
                deps = re.findall(r"<dependency>.*?<artifactId>([^<]+)</artifactId>.*?</dependency>", content, re.DOTALL)
                for dep_art in deps:
                    dep_art = dep_art.strip()
                    if dep_art in artifact_to_name and artifact_to_name[dep_art] != name:
                        mod.internal_dependencies.add(artifact_to_name[dep_art])
            except Exception:
                pass

    def _compute_topological_waves(
        self, prerequisites: Dict[str, Set[str]]
    ) -> Tuple[List[ModernizationWave], bool, List[str]]:
        # Kahn's algorithm by layers
        prereqs = {k: set(v) for k, v in prerequisites.items()}
        completed: Set[str] = set()
        waves: List[ModernizationWave] = []
        has_cycles = False
        cycle_nodes: List[str] = []

        wave_idx = 0
        while len(completed) < len(prereqs):
            # Find all nodes whose prerequisites are all satisfied
            current_wave_nodes = [
                node for node, reqs in prereqs.items()
                if node not in completed and reqs.issubset(completed)
            ]

            if not current_wave_nodes:
                # Cycle detected
                has_cycles = True
                cycle_nodes = [node for node in prereqs if node not in completed]
                # Force remaining into a cycle resolution wave
                waves.append(
                    ModernizationWave(
                        wave_index=wave_idx,
                        modules=sorted(cycle_nodes),
                        description=f"Wave {wave_idx} (Cyclic Cluster): Combined parallel resolution for {len(cycle_nodes)} modules",
                    )
                )
                break

            current_wave_nodes.sort()
            desc = self._describe_wave(wave_idx, current_wave_nodes)
            waves.append(
                ModernizationWave(
                    wave_index=wave_idx,
                    modules=current_wave_nodes,
                    description=desc,
                )
            )

            completed.update(current_wave_nodes)
            wave_idx += 1

        return waves, has_cycles, cycle_nodes

    def _describe_wave(self, index: int, modules: List[str]) -> str:
        if index == 0:
            return f"Wave 0 (Foundational): Low-level leaf modules / domain contracts ({', '.join(modules)})"
        elif index == 1:
            return f"Wave 1 (Persistence & Data Access): Infrastructure & DAL modules ({', '.join(modules)})"
        elif index == 2:
            return f"Wave 2 (Core Business Logic): Services & Integration modules ({', '.join(modules)})"
        else:
            return f"Wave {index} (Edge & Presentation): Web, Controller & Gateway modules ({', '.join(modules)})"

    def execute_plan(
        self,
        plan: WaveExecutionPlan,
        worker_func: Callable[[str, Path], bool],
        checkpoint_file: Optional[Path] = None,
    ) -> WaveCheckpoint:
        checkpoint = WaveCheckpoint(project_root=plan.root_dir)
        if checkpoint_file and checkpoint_file.is_file():
            try:
                data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
                checkpoint = WaveCheckpoint.from_dict(data)
            except Exception:
                pass

        for wave in plan.waves:
            if wave.wave_index in checkpoint.completed_waves:
                continue

            wave_failed = False
            for mod_name in wave.modules:
                if mod_name in checkpoint.completed_modules:
                    continue

                mod_path = Path(plan.root_dir) / mod_name
                try:
                    success = worker_func(mod_name, mod_path)
                    if success:
                        checkpoint.completed_modules.add(mod_name)
                    else:
                        checkpoint.failed_modules[mod_name] = "Worker reported failure"
                        wave_failed = True
                except Exception as e:
                    checkpoint.failed_modules[mod_name] = str(e)
                    wave_failed = True

            if not wave_failed:
                checkpoint.completed_waves.append(wave.wave_index)

            if checkpoint_file:
                checkpoint_file.write_text(json.dumps(checkpoint.to_dict(), indent=2), encoding="utf-8")

            if wave_failed:
                break

        return checkpoint
