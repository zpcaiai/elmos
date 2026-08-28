"""Browser scenario contracts and privacy-preserving evidence replay."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol

from .artifacts import ContentAddressedStore
from .errors import ContractViolation
from .models import ArtifactRef, Identity, digest_of


@dataclass(frozen=True, slots=True)
class BrowserStep:
    operation: str
    locator: str | None = None
    value: str | None = None
    assertion: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserScenario:
    scenario_id: str
    name: str
    preconditions: tuple[str, ...]
    steps: tuple[BrowserStep, ...]
    cleanup: tuple[BrowserStep, ...] = ()
    viewport: Mapping[str, int] = field(default_factory=lambda: {"width": 1280, "height": 720})
    device: str = "desktop-chromium"


@dataclass(frozen=True, slots=True)
class BrowserEvidence:
    scenario_id: str
    status: str
    artifact_refs: tuple[ArtifactRef, ...]
    console_errors: tuple[str, ...]
    failed_requests: tuple[str, ...]
    locator_resolutions: tuple[Mapping[str, Any], ...]
    trace_id: str | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {"scenario_id": self.scenario_id, "status": self.status, "artifact_refs": [ref.as_dict() for ref in self.artifact_refs], "console_errors": list(self.console_errors), "failed_requests": list(self.failed_requests), "locator_resolutions": [dict(item) for item in self.locator_resolutions], "trace_id": self.trace_id, "digest": self.digest}


class BrowserDriver(Protocol):
    def execute(self, step: BrowserStep) -> Mapping[str, Any]: ...

    def capture(self) -> Mapping[str, bytes | str]: ...


class ScenarioValidator:
    def validate(self, scenario: BrowserScenario) -> None:
        if not scenario.scenario_id or not scenario.name or not scenario.steps:
            raise ContractViolation("browser scenario requires identity and steps")
        for step in (*scenario.steps, *scenario.cleanup):
            if step.operation not in {"navigate", "click", "fill", "select", "assert_text", "assert_visible", "wait"}:
                raise ContractViolation("unsupported browser operation")
            if step.operation in {"click", "fill", "select", "assert_text", "assert_visible"} and not step.locator:
                raise ContractViolation("interactive browser step requires semantic locator")
        if scenario.viewport.get("width", 0) < 320 or scenario.viewport.get("height", 0) < 240:
            raise ContractViolation("browser viewport is too small")


class BrowserEvidenceRunner:
    def __init__(self, artifacts: ContentAddressedStore, *, secret_values: Iterable[str] = ()) -> None:
        self.artifacts = artifacts
        self.secret_values = tuple(value for value in secret_values if value)
        self.validator = ScenarioValidator()

    def run(self, identity: Identity, scenario: BrowserScenario, driver: BrowserDriver, *, trace_id: str | None = None) -> BrowserEvidence:
        self.validator.validate(scenario)
        resolutions: list[Mapping[str, Any]] = []
        console_errors: list[str] = []
        failed_requests: list[str] = []
        refs: list[ArtifactRef] = []
        status = "pass"
        try:
            for step in scenario.steps:
                result = driver.execute(step)
                if result.get("locator_resolution"):
                    resolutions.append(dict(result["locator_resolution"]))
                console_errors.extend(self._redact_list(result.get("console_errors", [])))
                failed_requests.extend(self._redact_list(result.get("failed_requests", [])))
                if result.get("ok") is False:
                    status = "fail"
                    break
        except Exception as error:
            status = "error"
            refs.append(self.artifacts.put(identity.tenant_id, str(error).encode(), kind="browser-error", media_type="text/plain"))
        finally:
            try:
                for step in scenario.cleanup:
                    driver.execute(step)
            except Exception as error:
                status = "error"
                refs.append(self.artifacts.put(identity.tenant_id, str(error).encode(), kind="browser-cleanup-error", media_type="text/plain"))
            try:
                for kind, value in driver.capture().items():
                    data = value.encode("utf-8") if isinstance(value, str) else value
                    refs.append(self.artifacts.put(identity.tenant_id, self._redact_bytes(data), kind=f"browser-{kind}"))
            except Exception as error:
                status = "error"
                refs.append(self.artifacts.put(identity.tenant_id, str(error).encode(), kind="browser-capture-error", media_type="text/plain"))
        if console_errors or failed_requests:
            status = "fail"
        body = {"scenario_id": scenario.scenario_id, "status": status, "artifact_refs": [ref.as_dict() for ref in refs], "console_errors": console_errors, "failed_requests": failed_requests, "locator_resolutions": resolutions, "trace_id": trace_id}
        return BrowserEvidence(scenario.scenario_id, status, tuple(refs), tuple(console_errors), tuple(failed_requests), tuple(resolutions), trace_id, digest_of(body))

    def replay(self, identity: Identity, scenario: BrowserScenario, driver: BrowserDriver) -> BrowserEvidence:
        return self.run(identity, scenario, driver)

    def _redact_bytes(self, data: bytes) -> bytes:
        text = data.decode("utf-8", errors="replace")
        for secret in self.secret_values:
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(?i)(password|token|authorization|api[_-]?key)(\s*[:=]\s*)[^\s,;]+", r"\1\2[REDACTED]", text)
        return text.encode("utf-8")

    def _redact_list(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [self._redact_bytes(str(value).encode()).decode() for value in values]
