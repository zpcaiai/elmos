from __future__ import annotations

import json
from pathlib import Path
import pytest

from elmos_spring_modernization.multi_module_wave_orchestrator import (
    MultiModuleWaveOrchestrator,
    WaveExecutionPlan,
    ModernizationWave,
    WaveCheckpoint,
)


def test_standalone_single_module(tmp_path: Path):
    orchestrator = MultiModuleWaveOrchestrator(tmp_path)
    plan = orchestrator.inspect_and_plan()

    assert plan.total_modules == 1
    assert len(plan.waves) == 1
    assert plan.waves[0].modules == ["."]
    assert not plan.has_cycles


def test_multi_module_dag_wave_layers(tmp_path: Path):
    # Setup a 4-tier monorepo:
    # root
    #  ├── domain-model (leaf: Wave 0)
    #  ├── dal-repo (depends on domain-model: Wave 1)
    #  ├── service-core (depends on dal-repo and domain-model: Wave 2)
    #  └── web-api (depends on service-core: Wave 3)

    root_pom = tmp_path / "pom.xml"
    root_pom.write_text(
        """<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>enterprise-parent</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>
  <modules>
    <module>web-api</module>
    <module>service-core</module>
    <module>dal-repo</module>
    <module>domain-model</module>
  </modules>
</project>""",
        encoding="utf-8",
    )

    for mod, deps in [
        ("domain-model", []),
        ("dal-repo", ["domain-model"]),
        ("service-core", ["dal-repo", "domain-model"]),
        ("web-api", ["service-core"]),
    ]:
        m_dir = tmp_path / mod
        m_dir.mkdir(parents=True)
        dep_xml = "".join(
            f"""
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>{d}</artifactId>
      <version>1.0.0</version>
    </dependency>"""
            for d in deps
        )
        (m_dir / "pom.xml").write_text(
            f"""<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>com.example</groupId>
    <artifactId>enterprise-parent</artifactId>
    <version>1.0.0</version>
  </parent>
  <artifactId>{mod}</artifactId>
  <dependencies>{dep_xml}
  </dependencies>
</project>""",
            encoding="utf-8",
        )

    orchestrator = MultiModuleWaveOrchestrator(tmp_path)
    plan = orchestrator.inspect_and_plan()

    assert plan.total_modules == 4
    assert len(plan.waves) == 4
    assert not plan.has_cycles

    # Verify topological order
    assert plan.waves[0].modules == ["domain-model"]
    assert plan.waves[1].modules == ["dal-repo"]
    assert plan.waves[2].modules == ["service-core"]
    assert plan.waves[3].modules == ["web-api"]


def test_cycle_detection_fail_safe(tmp_path: Path):
    root_pom = tmp_path / "pom.xml"
    root_pom.write_text(
        """<project>
  <modelVersion>4.0.0</modelVersion>
  <artifactId>cyclic-parent</artifactId>
  <modules>
    <module>mod-a</module>
    <module>mod-b</module>
  </modules>
</project>""",
        encoding="utf-8",
    )

    for mod, dep in [("mod-a", "mod-b"), ("mod-b", "mod-a")]:
        m_dir = tmp_path / mod
        m_dir.mkdir()
        (m_dir / "pom.xml").write_text(
            f"""<project>
  <artifactId>{mod}</artifactId>
  <dependencies>
    <dependency>
      <artifactId>{dep}</artifactId>
    </dependency>
  </dependencies>
</project>""",
            encoding="utf-8",
        )

    orchestrator = MultiModuleWaveOrchestrator(tmp_path)
    plan = orchestrator.inspect_and_plan()

    assert plan.has_cycles is True
    assert set(plan.cycle_nodes) == {"mod-a", "mod-b"}
    assert len(plan.waves) == 1
    assert "Cyclic Cluster" in plan.waves[0].description


def test_checkpoint_and_resume_execution(tmp_path: Path):
    root_pom = tmp_path / "pom.xml"
    root_pom.write_text(
        """<project>
  <modules>
    <module>m1</module>
    <module>m2</module>
  </modules>
</project>""",
        encoding="utf-8",
    )
    (tmp_path / "m1").mkdir()
    (tmp_path / "m1" / "pom.xml").write_text("<project><artifactId>m1</artifactId></project>", encoding="utf-8")
    (tmp_path / "m2").mkdir()
    (tmp_path / "m2" / "pom.xml").write_text(
        """<project>
  <artifactId>m2</artifactId>
  <dependencies>
    <dependency><artifactId>m1</artifactId></dependency>
  </dependencies>
</project>""",
        encoding="utf-8",
    )

    orchestrator = MultiModuleWaveOrchestrator(tmp_path)
    plan = orchestrator.inspect_and_plan()

    checkpoint_file = tmp_path / "checkpoint.json"

    # Execution run 1: m1 succeeds, m2 fails
    def worker_run1(mod_name: str, mod_dir: Path) -> bool:
        if mod_name == "m1":
            return True
        return False

    cp1 = orchestrator.execute_plan(plan, worker_run1, checkpoint_file)
    assert "m1" in cp1.completed_modules
    assert "m2" in cp1.failed_modules
    assert 0 in cp1.completed_waves
    assert 1 not in cp1.completed_waves

    # Execution run 2 (Resume): m1 is skipped, m2 succeeds
    executed_mods = []

    def worker_run2(mod_name: str, mod_dir: Path) -> bool:
        executed_mods.append(mod_name)
        return True

    cp2 = orchestrator.execute_plan(plan, worker_run2, checkpoint_file)
    assert executed_mods == ["m2"]
    assert "m2" in cp2.completed_modules
    assert 1 in cp2.completed_waves
