from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, main, mock


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = ROOT / "scripts/batch30/run_spring_production_gate.py"
SPEC = importlib.util.spec_from_file_location("spring_production_gate_launcher", LAUNCHER_PATH)
assert SPEC is not None and SPEC.loader is not None
LAUNCHER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LAUNCHER
SPEC.loader.exec_module(LAUNCHER)


class ExecutedMake(Exception):
    pass


class SpringProductionGateLauncherTests(TestCase):
    @staticmethod
    def environment(target: str) -> dict[str, str]:
        values = dict(LAUNCHER.BASE_ENVIRONMENT)
        for name in LAUNCHER.TARGET_INPUTS[target]:
            values[name] = {
                "SPRING_EXPECTED_REVISION": "a" * 40,
                "SPRING_OBSERVER_BUNDLE_DIGEST": "sha256:" + "b" * 64,
                "SPRING_TRUST_STORE_DIGEST": "sha256:" + "c" * 64,
                "SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST": "sha256:" + "d" * 64,
                "SPRING_WEB_IMAGE_DIGEST": "sha256:" + "e" * 64,
                "SPRING_WORKER_IMAGE_DIGEST": "sha256:" + "f" * 64,
            }.get(name, f"value-{name.lower()}")
        return values

    def test_rejects_make_flags_and_additional_makefiles_before_launch(self) -> None:
        with mock.patch.object(LAUNCHER, "launch") as launch:
            self.assertEqual(
                2,
                LAUNCHER.main(
                    ["spring-launch-gate", "-f", "/unapproved/Makefile"]
                ),
            )
        launch.assert_not_called()

    def test_rejects_make_control_environment(self) -> None:
        environment = self.environment("spring-launch-gate")
        for name in ("MAKEFLAGS", "MAKEFILES", "MAKEFILE_LIST", "SHELL"):
            with self.subTest(name=name):
                supplied = dict(environment)
                supplied[name] = "unapproved"
                with self.assertRaisesRegex(
                    LAUNCHER.ProductionGateLauncherError, "unknown keys"
                ):
                    LAUNCHER._controlled_environment(
                        "spring-launch-gate", supplied
                    )

    def test_rejects_shell_and_make_syntax_in_every_target_input(self) -> None:
        attacks = (
            "$(shell id)",
            "$(id)",
            'value";id;#',
            "value\nnext",
            " value",
            "",
        )
        for target, names in LAUNCHER.TARGET_INPUTS.items():
            baseline = self.environment(target)
            for name in names:
                for attack in attacks:
                    with self.subTest(target=target, name=name, attack=attack):
                        supplied = dict(baseline)
                        supplied[name] = attack
                        with self.assertRaisesRegex(
                            LAUNCHER.ProductionGateLauncherError,
                            f"safe non-empty {name}",
                        ):
                            LAUNCHER._controlled_environment(target, supplied)

    def test_executes_one_fixed_makefile_with_only_controlled_environment(self) -> None:
        environment = self.environment("spring-launch-gate")
        topology = mock.Mock()
        topology.validate_observer_execution.return_value = []
        with mock.patch.object(
            LAUNCHER, "_load_topology_validator", return_value=topology
        ), mock.patch.object(
            LAUNCHER.os, "execve", side_effect=ExecutedMake
        ) as execve:
            with self.assertRaises(ExecutedMake):
                LAUNCHER.launch("spring-launch-gate", environment)

        topology.validate_observer_execution.assert_called_once_with(
            revision="a" * 40,
            expected_digest="sha256:" + "b" * 64,
        )
        topology.validate_trusted_system_executable.assert_called_once_with(
            Path("/usr/bin/make"), label="production GNU make"
        )
        self.assertEqual(
            [
                "/usr/bin/make",
                "--no-print-directory",
                "-C",
                str(ROOT),
                "-f",
                "Makefile.batch30",
                "spring-launch-gate",
            ],
            execve.call_args.args[1],
        )
        self.assertEqual(environment, execve.call_args.args[2])


if __name__ == "__main__":
    main()
