from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunnerProfile:
    name: str
    python_versions: tuple[str, ...]
    operating_system: str
    gpu: bool = False
    notebook: bool = False


@dataclass(frozen=True)
class RunnerRoutingDecision:
    status: str
    runner_profile: str | None
    blockers: tuple[str, ...]
    policy: dict[str, str | bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "runnerProfile": self.runner_profile,
            "blockers": list(self.blockers),
            "policy": self.policy,
        }


class PythonRunnerRouter:
    PROFILES = (
        RunnerProfile("PYTHON_LEGACY_LINUX", ("2.7", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10"), "LINUX"),
        RunnerProfile("PYTHON_MODERN_CPU", ("3.10", "3.11", "3.12", "3.13", "3.14"), "LINUX"),
        RunnerProfile("PYTHON_MODERN_GPU", ("3.10", "3.11", "3.12", "3.13"), "LINUX", gpu=True),
        RunnerProfile("PYTHON_WINDOWS", ("3.10", "3.11", "3.12", "3.13", "3.14"), "WINDOWS"),
        RunnerProfile("PYTHON_NOTEBOOK", ("3.10", "3.11", "3.12", "3.13", "3.14"), "LINUX", notebook=True),
    )

    def route(
        self,
        python_version: str,
        operating_system: str = "LINUX",
        *,
        requires_gpu: bool = False,
        notebook: bool = False,
    ) -> RunnerRoutingDecision:
        operating_system = operating_system.upper()
        blockers: list[str] = []
        if python_version == "2.7" and (operating_system != "LINUX" or requires_gpu or notebook):
            blockers.append("LEGACY_PYTHON_RUNNER_REQUIRED")
        candidates = [
            profile
            for profile in self.PROFILES
            if python_version in profile.python_versions
            and profile.operating_system == operating_system
            and profile.gpu == requires_gpu
            and profile.notebook == notebook
        ]
        if not candidates:
            if requires_gpu:
                blockers.append("GPU_RUNNER_REQUIRED")
            elif operating_system == "WINDOWS":
                blockers.append("WINDOWS_RUNNER_UNAVAILABLE")
            elif notebook:
                blockers.append("NOTEBOOK_RUNNER_REQUIRED")
            else:
                blockers.append("PYTHON_INTERPRETER_UNAVAILABLE")
        selected = candidates[0].name if candidates else None
        if python_version == "2.7" and selected != "PYTHON_LEGACY_LINUX":
            blockers.append("LEGACY_PYTHON_RUNNER_REQUIRED")
            selected = None
        return RunnerRoutingDecision(
            status="ROUTED" if selected and not blockers else "BLOCKED",
            runner_profile=selected,
            blockers=tuple(sorted(set(blockers))),
            policy={
                "network": "DENY_BY_DEFAULT",
                "secrets": "NONE_UNLESS_LEASED",
                "rootless": True,
                "customerCodeInControlPlane": False,
            },
        )
