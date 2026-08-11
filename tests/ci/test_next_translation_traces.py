from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tooling" / "validate_next_translation_traces.py"
SPEC = importlib.util.spec_from_file_location(
    "validate_next_translation_traces", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Next translation trace validator could not be loaded")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class NextTranslationTraceTest(unittest.TestCase):
    def fixture(
        self,
        root: Path,
        *,
        include_assets: bool,
        missing_trace: bool = False,
        extra_trace: bool = False,
    ) -> Path:
        (root / "routes" / "java-to-go").mkdir(parents=True)
        (root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
        (root / "routes" / "inventory.json").write_text("{}\n", encoding="utf-8")
        (root / "routes" / "java-to-go" / "route.json").write_text(
            "{}\n", encoding="utf-8"
        )
        source_handlers = [
            root
            / "apps"
            / "web-console"
            / "app"
            / "api"
            / "capabilities"
            / "translation"
            / "route.ts",
            root
            / "apps"
            / "web-console"
            / "app"
            / "api"
            / "translation"
            / "health"
            / "route.ts",
        ]
        for handler in source_handlers:
            handler.parent.mkdir(parents=True, exist_ok=True)
            handler.write_text("export const GET = () => new Response();\n")
        dist = root / "apps" / "web-console" / ".next"
        traces = [
            dist
            / "server"
            / "app"
            / "api"
            / "capabilities"
            / "translation"
            / "route.js.nft.json",
            dist
            / "server"
            / "app"
            / "api"
            / "translation"
            / "health"
            / "route.js.nft.json",
        ]
        if missing_trace:
            traces.pop()
        if extra_trace:
            traces.append(
                dist
                / "server"
                / "app"
                / "api"
                / "translation"
                / "orphan"
                / "route.js.nft.json"
            )
        assets = [
            root / "pom.xml",
            root / "routes" / "inventory.json",
            root / "routes" / "java-to-go" / "route.json",
        ]
        for trace in traces:
            trace.parent.mkdir(parents=True, exist_ok=True)
            files = (
                [os.path.relpath(path, trace.parent) for path in assets]
                if include_assets
                else ["route.js"]
            )
            trace.write_text(json.dumps({"version": 1, "files": files}) + "\n")
        return dist

    def test_every_translation_server_trace_carries_contract_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = self.fixture(root, include_assets=True)
            with mock.patch.object(
                validator,
                "required_assets",
                side_effect=lambda _: {
                    (root / "pom.xml").resolve(),
                    (root / "routes" / "inventory.json").resolve(),
                    (root / "routes" / "java-to-go" / "route.json").resolve(),
                },
            ):
                report = validator.validate(root, dist)
            self.assertEqual("PASSED", report["status"])
            self.assertEqual(2, report["trace_count"])
            self.assertEqual("NOT_RUN", report["runtime_status"])

    def test_missing_contract_asset_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = self.fixture(root, include_assets=False)
            with (
                mock.patch.object(
                    validator,
                    "required_assets",
                    side_effect=lambda _: {
                        (root / "pom.xml").resolve(),
                    },
                ),
                self.assertRaisesRegex(ValueError, "TRACE_ASSETS_MISSING"),
            ):
                validator.validate(root, dist)

    def test_missing_handler_trace_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = self.fixture(root, include_assets=True, missing_trace=True)
            with (
                mock.patch.object(validator, "required_assets", return_value=set()),
                self.assertRaisesRegex(
                    ValueError,
                    "TRACE_SET_MISMATCH:missing=.*translation/health",
                ),
            ):
                validator.validate(root, dist)

    def test_extra_handler_trace_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = self.fixture(root, include_assets=True, extra_trace=True)
            with (
                mock.patch.object(validator, "required_assets", return_value=set()),
                self.assertRaisesRegex(
                    ValueError,
                    "TRACE_SET_MISMATCH:.*extra=.*translation/orphan",
                ),
            ):
                validator.validate(root, dist)


if __name__ == "__main__":
    unittest.main()
