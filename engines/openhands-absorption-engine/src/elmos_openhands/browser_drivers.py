"""Real Playwright browser sessions, device matrix and flake classification."""

from __future__ import annotations

import json
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .browser import BrowserDriver, BrowserEvidence, BrowserEvidenceRunner, BrowserScenario, BrowserStep
from .errors import ContractViolation, NotConfigured
from .models import Identity, digest_of


@dataclass(frozen=True, slots=True)
class BrowserProfile:
    name: str
    engine: str = "chromium"
    viewport: Mapping[str, int] = field(default_factory=lambda: {"width": 1280, "height": 720})
    device_descriptor: str | None = None
    locale: str = "en-US"
    timezone_id: str = "UTC"
    color_scheme: str = "light"
    reduced_motion: str = "reduce"
    ignore_https_errors: bool = False
    mask_locators: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name or self.engine not in {"chromium", "firefox", "webkit"}:
            raise ContractViolation("browser profile identity/engine is invalid")
        if self.viewport.get("width", 0) < 320 or self.viewport.get("height", 0) < 240:
            raise ContractViolation("browser profile viewport is too small")
        if self.ignore_https_errors:
            raise ContractViolation("production browser profiles cannot ignore TLS errors")


DEFAULT_BROWSER_PROFILES = (
    BrowserProfile("desktop-chromium", "chromium", {"width": 1440, "height": 900}),
    BrowserProfile("desktop-firefox", "firefox", {"width": 1440, "height": 900}),
    BrowserProfile("desktop-webkit", "webkit", {"width": 1440, "height": 900}),
    BrowserProfile("mobile-chromium", "chromium", {"width": 390, "height": 844}, "iPhone 13"),
)


class PlaywrightBrowserDriver:
    """Playwright driver implementing the BrowserDriver evidence contract."""

    def __init__(
        self,
        profile: BrowserProfile,
        *,
        base_url: str,
        traceparent: str | None = None,
        playwright_factory: Callable[[], Any] | None = None,
        launch_options: Mapping[str, Any] | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ContractViolation("browser base URL must be HTTP(S)")
        if base_url.startswith("http://") and not re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?(?:/|$)", base_url):
            raise ContractViolation("cleartext browser URLs are allowed only for local qualification")
        self.profile = profile
        self.base_url = base_url.rstrip("/")
        self.traceparent = traceparent
        self._temporary = tempfile.TemporaryDirectory(prefix="elmos-browser-")
        self._console: list[dict[str, Any]] = []
        self._requests: list[dict[str, Any]] = []
        self._locator_resolutions: list[dict[str, Any]] = []
        self._sensitive_locators: set[str] = set(profile.mask_locators)
        self._captured = False
        try:
            if playwright_factory is None:
                from playwright.sync_api import sync_playwright

                playwright_factory = sync_playwright
            self._playwright = playwright_factory().start()
        except ImportError as error:  # pragma: no cover - optional production dependency
            self._temporary.cleanup()
            raise NotConfigured("Playwright is required for browser/device execution") from error
        engine = getattr(self._playwright, profile.engine)
        options = {"headless": True, **dict(launch_options or {})}
        if options.get("headless") is False:
            raise ContractViolation("production evidence driver must run in controlled headless mode")
        self._browser = engine.launch(**options)
        context_options: dict[str, Any] = {
            "viewport": dict(profile.viewport), "locale": profile.locale, "timezone_id": profile.timezone_id,
            "color_scheme": profile.color_scheme, "reduced_motion": profile.reduced_motion,
            "ignore_https_errors": False, "record_video_dir": self._temporary.name,
        }
        if profile.device_descriptor:
            descriptor = self._playwright.devices.get(profile.device_descriptor)
            if descriptor is None:
                self.close()
                raise NotConfigured("Playwright device descriptor is unavailable: " + profile.device_descriptor)
            context_options = {**descriptor, **context_options, "viewport": dict(profile.viewport)}
        if traceparent:
            context_options["extra_http_headers"] = {"traceparent": traceparent}
        self._context = self._browser.new_context(**context_options)
        self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self._page = self._context.new_page()
        self._page.on("console", self._on_console)
        self._page.on("response", self._on_response)

    def execute(self, step: BrowserStep) -> Mapping[str, Any]:
        if self._captured:
            raise ContractViolation("browser session is already finalized")
        started = time.monotonic()
        result: dict[str, Any] = {"ok": True, "operation": step.operation}
        if step.operation == "navigate":
            target = self._url(step.value or step.locator or "/")
            response = self._page.goto(target, wait_until="networkidle")
            result["http_status"] = None if response is None else response.status
            if response is not None and response.status >= 400:
                result["ok"] = False
        elif step.operation == "wait":
            milliseconds = min(30_000, max(0, int(float(step.value or "0") * 1000)))
            self._page.wait_for_timeout(milliseconds)
        else:
            locator, resolution = self._locator(step.locator or "")
            if step.sensitive:
                self._sensitive_locators.add(step.locator or "")
            result["locator_resolution"] = resolution
            self._locator_resolutions.append(resolution)
            if step.operation == "click":
                locator.click()
            elif step.operation == "fill":
                locator.fill(step.value or "")
            elif step.operation == "select":
                locator.select_option(step.value or "")
            elif step.operation == "assert_text":
                actual = locator.inner_text()
                expected = step.assertion if step.assertion is not None else step.value or ""
                result.update({"actual": actual, "expected": expected, "ok": expected in actual})
            elif step.operation == "assert_visible":
                result["ok"] = bool(locator.is_visible())
            else:
                raise ContractViolation("unsupported browser operation")
        result["duration_ms"] = int((time.monotonic() - started) * 1000)
        result["console_errors"] = [entry["text"] for entry in self._console if entry["type"] == "error"]
        result["failed_requests"] = [entry["url"] for entry in self._requests if int(entry["status"]) >= 400]
        return result

    def capture(self) -> Mapping[str, bytes | str]:
        if self._captured:
            return {}
        self._captured = True
        evidence: dict[str, bytes | str] = {}
        try:
            masked = self._apply_privacy_masks()
            evidence["screenshot.png"] = self._page.screenshot(full_page=True)
            evidence["dom.html"] = self._page.content()
            evidence["accessibility.json"] = json.dumps(self._accessibility_snapshot(), ensure_ascii=False, sort_keys=True)
            evidence["console.json"] = json.dumps(self._console, ensure_ascii=False, sort_keys=True)
            evidence["network.json"] = json.dumps(self._requests, ensure_ascii=False, sort_keys=True)
            evidence["locators.json"] = json.dumps(self._locator_resolutions, ensure_ascii=False, sort_keys=True)
            evidence["privacy.json"] = json.dumps({"masked_locators": masked, "status": "APPLIED"}, ensure_ascii=False, sort_keys=True)
            trace_path = Path(self._temporary.name) / "trace.zip"
            self._context.tracing.stop(path=str(trace_path))
            video = getattr(self._page, "video", None)
            self._page.close()
            self._context.close()
            self._browser.close()
            if trace_path.is_file():
                evidence["trace.zip"] = trace_path.read_bytes()
            if video is not None:
                try:
                    video_path = Path(video.path())
                    if video_path.is_file():
                        evidence["video.webm"] = video_path.read_bytes()
                except Exception:  # noqa: BLE001 - unavailable video is explicit NOT_RUN evidence
                    evidence["video-unavailable.json"] = json.dumps({"status": "NOT_RUN", "reason": "video finalization unavailable"})
        finally:
            try:
                self._playwright.stop()
            finally:
                self._temporary.cleanup()
        return evidence

    def close(self) -> None:
        if self._captured:
            return
        try:
            self.capture()
        except Exception:  # noqa: BLE001 - cleanup must run even when capture fails
            try:
                self._playwright.stop()
            finally:
                self._temporary.cleanup()

    def _locator(self, value: str) -> tuple[Any, dict[str, Any]]:
        if not value or value.startswith(("css=", "xpath=")):
            raise ContractViolation("browser evidence requires a semantic locator")
        strategy, separator, selector = value.partition("=")
        if not separator or not selector:
            raise ContractViolation("semantic locator must use role=, label=, text=, placeholder= or testid=")
        if strategy == "role":
            role, _, name = selector.partition("|")
            locator = self._page.get_by_role(role, name=name or None)
        elif strategy == "label":
            locator = self._page.get_by_label(selector)
        elif strategy == "text":
            locator = self._page.get_by_text(selector, exact=True)
        elif strategy == "placeholder":
            locator = self._page.get_by_placeholder(selector)
        elif strategy == "testid":
            locator = self._page.get_by_test_id(selector)
        else:
            raise ContractViolation("unsupported semantic locator strategy")
        count = locator.count()
        if count != 1:
            raise ContractViolation(f"semantic locator resolved to {count} elements")
        resolution = {"locator": value, "strategy": strategy, "count": count, "page_url": self._page.url}
        return locator, resolution

    def _url(self, target: str) -> str:
        if target.startswith("/"):
            return self.base_url + target
        if not target.startswith(self.base_url):
            raise ContractViolation("browser navigation escapes the configured origin")
        return target

    def _accessibility_snapshot(self) -> Any:
        accessibility = getattr(self._page, "accessibility", None)
        if accessibility is not None and callable(getattr(accessibility, "snapshot", None)):
            return accessibility.snapshot(interesting_only=False)
        locator = self._page.locator("body")
        if callable(getattr(locator, "aria_snapshot", None)):
            return {"aria": locator.aria_snapshot()}
        return {"status": "NOT_RUN", "reason": "accessibility snapshot API unavailable"}

    def _apply_privacy_masks(self) -> list[str]:
        masked: list[str] = []
        for value in sorted(self._sensitive_locators):
            locator, _ = self._locator(value)
            locator.evaluate(
                """element => {
                  if ('value' in element) element.value = '[REDACTED]';
                  element.textContent = '[REDACTED]';
                  element.setAttribute('aria-label', '[REDACTED]');
                  element.setAttribute('data-elmos-masked', 'true');
                }"""
            )
            masked.append(value)
        return masked

    def _on_console(self, message: Any) -> None:
        self._console.append({"type": str(message.type), "text": str(message.text), "location": dict(getattr(message, "location", {}) or {})})

    def _on_response(self, response: Any) -> None:
        request = getattr(response, "request", None)
        self._requests.append({"url": str(response.url), "status": int(response.status), "method": str(getattr(request, "method", "GET")), "resource_type": str(getattr(request, "resource_type", "unknown"))})


@dataclass(frozen=True, slots=True)
class BrowserMatrixResult:
    scenario_id: str
    profiles: Mapping[str, BrowserEvidence]
    classification: str
    digest: str
    certification: str = "NOT_CERTIFIED"


class BrowserMatrixRunner:
    def __init__(self, evidence_runner: BrowserEvidenceRunner, *, attempts: int = 2) -> None:
        if attempts < 1 or attempts > 5:
            raise ContractViolation("browser retry attempts must be in [1,5]")
        self.evidence_runner = evidence_runner
        self.attempts = attempts

    def run(
        self,
        identity: Identity,
        scenario: BrowserScenario,
        profiles: tuple[BrowserProfile, ...],
        driver_factory: Callable[[BrowserProfile], BrowserDriver],
        *,
        trace_id: str | None = None,
    ) -> BrowserMatrixResult:
        if not profiles:
            raise ContractViolation("browser matrix requires at least one profile")
        final: dict[str, BrowserEvidence] = {}
        outcomes: dict[str, list[str]] = {}
        for profile in profiles:
            outcomes[profile.name] = []
            for _ in range(self.attempts):
                evidence = self.evidence_runner.run(identity, scenario, driver_factory(profile), trace_id=trace_id)
                outcomes[profile.name].append(evidence.status)
                final[profile.name] = evidence
                if evidence.status == "pass":
                    break
        values = [status for statuses in outcomes.values() for status in statuses]
        if any("pass" in statuses and any(status != "pass" for status in statuses) for statuses in outcomes.values()):
            classification = "FLAKY_BLOCKED"
        elif all(status == "pass" for status in values):
            classification = "PASS"
        else:
            classification = "FAIL"
        body = {"scenario": scenario.scenario_id, "outcomes": outcomes, "evidence": {name: item.digest for name, item in final.items()}, "classification": classification}
        return BrowserMatrixResult(scenario.scenario_id, final, classification, digest_of(body))
