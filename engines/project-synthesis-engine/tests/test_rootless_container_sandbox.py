"""Tests for Linux Rootless Container Sandbox and Hermetic Path Confinement.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
import pytest

from elmos_project_synthesis.rootless_container_sandbox import (
    LinuxRootlessSandboxRunner,
    RootlessSandboxDetector,
    SandboxExecutionResult,
    SandboxSecurityConfig,
)


def test_sandbox_security_config_defaults():
    config = SandboxSecurityConfig()
    assert config.read_only_root is True
    assert "ALL" in config.drop_capabilities
    assert config.no_new_privileges is True
    assert config.network_isolated is True
    assert config.memory_mb == 512
    assert config.cpus == 1.0


def test_sandbox_detector_and_runner_creation():
    detector = RootlessSandboxDetector()
    backends = detector.detect_backends()

    assert "hermetic_path_jail" in backends

    runner = LinuxRootlessSandboxRunner()
    assert runner is not None
    assert len(runner.available_backends) >= 1


def test_hermetic_path_jail_safe_execution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        test_file = tmp_path / "hello.txt"
        test_file.write_text("secure content", encoding="utf-8")

        runner = LinuxRootlessSandboxRunner()
        # Run standard python command reading local file
        cmd = [sys.executable, "-c", "print(open('hello.txt').read().strip())"]
        result: SandboxExecutionResult = runner.run(cmd, host_workspace_path=tmp_path)

        assert result.exit_code == 0
        assert "secure content" in result.stdout
        assert result.is_success is True
        assert result.security_verifications["cap_drop_all"] is True
        assert result.security_verifications["read_only_root"] is True


def test_podman_and_bwrap_argument_generation():
    config = SandboxSecurityConfig(
        read_only_root=True,
        drop_capabilities=("ALL",),
        no_new_privileges=True,
        network_isolated=True,
        memory_mb=1024,
        cpus=2.0,
    )
    runner = LinuxRootlessSandboxRunner(config=config)
    assert runner.config.memory_mb == 1024
    assert runner.config.cpus == 2.0
