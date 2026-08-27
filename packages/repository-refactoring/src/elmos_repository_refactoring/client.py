"""Skill 22 — component, route, state and platform work on the client side.

Client refactors fail differently from server refactors.  The compiler often
still passes; what breaks is a screen, a deep link, a payment sheet, or a
capability that exists on one platform and not another.  Three things follow
from that and are enforced here:

* **A visual difference cannot be adjudicated by this core.**  There is no
  renderer, so :class:`VisualCheck` is always ``not-run`` until an executor
  supplies screenshots, and :func:`decide` treats a missing visual result as
  blocking rather than as "no visual change".
* **A capability missing on a target platform is a hard finding.**  The
  matrix in :data:`PLATFORM_CAPABILITIES` records what each target actually
  supports; a component that uses a capability the target lacks needs an
  adapter, and :func:`platform_matrix` says which and why instead of
  reporting a build error later.
* **Some surfaces are never "just a refactor".**  Analytics, experiments,
  deep links, permissions, payments and native bridges each get their own
  verification entry (:func:`sensitive_surfaces`), because a renamed handler
  in any of them silently stops reporting rather than failing loudly.

The a11y checks here are static and deliberately conservative: they find
missing text alternatives and labels, which is a real class of regression a
refactor introduces, and they never claim a page is *accessible*.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .contracts import RiskClass, sha256_payload
from .patch import PatchSet
from .workspace import WorkspaceSnapshot


class Platform(StrEnum):
    WEB = "web"
    IOS = "ios"
    ANDROID = "android"
    DESKTOP = "desktop"
    WECHAT_MINIPROGRAM = "wechat-miniprogram"
    ALIPAY_MINIPROGRAM = "alipay-miniprogram"
    DOUYIN_MINIPROGRAM = "douyin-miniprogram"
    XIAOHONGSHU_MINIPROGRAM = "xiaohongshu-miniprogram"


class Capability(StrEnum):
    DOM = "dom"
    LOCAL_STORAGE = "local-storage"
    WEB_SOCKET = "web-socket"
    SERVICE_WORKER = "service-worker"
    DYNAMIC_IMPORT = "dynamic-import"
    FILE_SYSTEM = "file-system"
    CAMERA = "camera"
    PUSH_NOTIFICATION = "push-notification"
    NATIVE_PAYMENT = "native-payment"
    DEEP_LINK = "deep-link"
    BACKGROUND_TASK = "background-task"


#: What each target genuinely supports.  A miniprogram host is not a browser:
#: no DOM, no service worker, and no dynamic import of arbitrary code, which
#: is exactly what a "just port the components" plan trips over.
PLATFORM_CAPABILITIES: Mapping[Platform, frozenset[Capability]] = {
    Platform.WEB: frozenset(Capability),
    Platform.DESKTOP: frozenset(Capability) - {Capability.NATIVE_PAYMENT},
    Platform.IOS: frozenset(
        {
            Capability.LOCAL_STORAGE,
            Capability.WEB_SOCKET,
            Capability.FILE_SYSTEM,
            Capability.CAMERA,
            Capability.PUSH_NOTIFICATION,
            Capability.NATIVE_PAYMENT,
            Capability.DEEP_LINK,
            Capability.BACKGROUND_TASK,
        }
    ),
    Platform.ANDROID: frozenset(
        {
            Capability.LOCAL_STORAGE,
            Capability.WEB_SOCKET,
            Capability.FILE_SYSTEM,
            Capability.CAMERA,
            Capability.PUSH_NOTIFICATION,
            Capability.NATIVE_PAYMENT,
            Capability.DEEP_LINK,
            Capability.BACKGROUND_TASK,
        }
    ),
    Platform.WECHAT_MINIPROGRAM: frozenset(
        {
            Capability.LOCAL_STORAGE,
            Capability.WEB_SOCKET,
            Capability.CAMERA,
            Capability.NATIVE_PAYMENT,
            Capability.DEEP_LINK,
        }
    ),
    Platform.ALIPAY_MINIPROGRAM: frozenset(
        {
            Capability.LOCAL_STORAGE,
            Capability.WEB_SOCKET,
            Capability.CAMERA,
            Capability.NATIVE_PAYMENT,
            Capability.DEEP_LINK,
        }
    ),
    Platform.DOUYIN_MINIPROGRAM: frozenset(
        {Capability.LOCAL_STORAGE, Capability.WEB_SOCKET, Capability.CAMERA, Capability.DEEP_LINK}
    ),
    Platform.XIAOHONGSHU_MINIPROGRAM: frozenset(
        {Capability.LOCAL_STORAGE, Capability.CAMERA, Capability.DEEP_LINK}
    ),
}

_CAPABILITY_MARKERS: Mapping[Capability, tuple[re.Pattern[str], ...]] = {
    Capability.DOM: (
        re.compile(r"\bdocument\.(?:getElementById|querySelector|createElement)\b"),
        re.compile(r"\bwindow\.(?:addEventListener|location)\b"),
    ),
    Capability.LOCAL_STORAGE: (re.compile(r"\b(?:localStorage|sessionStorage)\b"),),
    Capability.WEB_SOCKET: (re.compile(r"\bnew\s+WebSocket\s*\("),),
    Capability.SERVICE_WORKER: (re.compile(r"navigator\.serviceWorker"),),
    Capability.DYNAMIC_IMPORT: (re.compile(r"\bimport\s*\([^)]"), re.compile(r"\brequire\.ensure\b")),
    Capability.FILE_SYSTEM: (re.compile(r"\bnew\s+File\s*\(|FileReader\b|fs\.(?:readFile|writeFile)"),),
    Capability.CAMERA: (re.compile(r"getUserMedia|chooseImage|ImagePicker"),),
    Capability.PUSH_NOTIFICATION: (re.compile(r"\bNotification\s*\(|registerForRemoteNotifications"),),
    Capability.NATIVE_PAYMENT: (re.compile(r"requestPayment|ApplePay|GooglePay|PaymentRequest"),),
    Capability.DEEP_LINK: (re.compile(r"deepLink|universalLink|navigateTo\s*\(|Linking\.openURL"),),
    Capability.BACKGROUND_TASK: (re.compile(r"BackgroundTask|WorkManager|setInterval\s*\(\s*\w+\s*,\s*\d{5,}"),),
}

#: Surfaces where a rename silently stops reporting instead of failing.
_SENSITIVE_SURFACES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "analytics",
        re.compile(r"\b(?:track|logEvent|analytics|reportEvent|gtag|sensors)\s*[.(]", re.IGNORECASE),
        "an analytics call whose event name changed keeps compiling and stops reporting",
    ),
    (
        "experiment",
        re.compile(r"\b(?:experiment|ab_?test|featureFlag|variant)\b", re.IGNORECASE),
        "an experiment key that no longer matches puts every user in the default bucket",
    ),
    (
        "deep-link",
        re.compile(r"deepLink|universalLink|scheme\s*[:=]|route\s*[:=]\s*[\"']/"),
        "a changed route breaks links already sent to users; nothing in the build notices",
    ),
    (
        "permission",
        re.compile(r"\b(?:requestPermission|checkPermission|AndroidManifest|NSCameraUsageDescription)\b"),
        "a permission prompt moved or removed changes what the app may do at runtime",
    ),
    (
        "payment",
        re.compile(r"requestPayment|checkout|ApplePay|GooglePay|PaymentRequest|订单|支付", re.IGNORECASE),
        "a payment path needs its own verification; a silent failure here costs money",
    ),
    (
        "native-bridge",
        re.compile(r"postMessage\s*\(|JSBridge|WebViewJavascriptBridge|invokeNative|wx\.\w+"),
        "the native side is versioned separately; a changed message shape fails only at runtime",
    ),
)

_COMPONENT = re.compile(
    r"\b(?:export\s+(?:default\s+)?(?:function|class|const)\s+(?P<js>[A-Z]\w*)"
    r"|defineComponent\s*\(\s*\{\s*name\s*:\s*[\"'](?P<vue>[\w-]+)"
    r"|class\s+(?P<dart>\w+)\s+extends\s+(?:StatelessWidget|StatefulWidget))"
)
_ROUTE = re.compile(r"[\"'](/[\w\-/:{}\[\]]*)[\"']\s*(?:,|:|=>|\})")
_CLASS_COMPONENT = re.compile(r"\bclass\s+(\w+)\s+extends\s+(?:React\.)?(?:Pure)?Component\b")
_HOOK = re.compile(r"\buse[A-Z]\w*\s*\(")

_A11Y_CHECKS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "image-without-text-alternative",
        re.compile(r"<img(?![^>]*\balt\s*=)[^>]*>", re.IGNORECASE),
        "an image with no alt attribute is invisible to a screen reader",
    ),
    (
        "control-without-label",
        re.compile(r"<(?:button|a)(?![^>]*aria-label)[^>]*>\s*(?:<[^>]+>\s*)*</(?:button|a)>", re.IGNORECASE),
        "an empty control with no aria-label announces nothing",
    ),
    (
        "positive-tabindex",
        re.compile(r"tabindex\s*=\s*[\"']?[1-9]", re.IGNORECASE),
        "a positive tabindex overrides document order and breaks keyboard navigation",
    ),
    (
        "input-without-label",
        re.compile(r"<input(?![^>]*(?:aria-label|id\s*=))[^>]*>", re.IGNORECASE),
        "an input with neither a label association nor an aria-label",
    ),
)

_CLIENT_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".dart", ".wxml", ".wxss", ".axml")


@dataclass(frozen=True, slots=True)
class ComponentNode:
    name: str
    path: str
    framework: str
    stateful: bool
    capabilities: tuple[Capability, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "framework": self.framework,
            "stateful": self.stateful,
            "capabilities": [item.value for item in self.capabilities],
        }


@dataclass(frozen=True, slots=True)
class PlatformGap:
    platform: Platform
    capability: Capability
    component: str
    path: str
    adapter: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "platform": self.platform.value,
            "capability": self.capability.value,
            "component": self.component,
            "path": self.path,
            "adapterRequired": self.adapter,
        }


@dataclass(frozen=True, slots=True)
class ClientFinding:
    rule_id: str
    path: str
    line: int
    message: str
    blocking: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "blocking": self.blocking,
        }


@dataclass(frozen=True, slots=True)
class VisualCheck:
    """A visual comparison this core cannot make on its own."""

    journey: str
    status: str = "not-run"
    difference: str = ""
    threshold: str = "0.01"

    @property
    def decided(self) -> bool:
        return self.status in ("pass", "fail")

    def to_payload(self) -> dict[str, Any]:
        return {
            "journey": self.journey,
            "status": self.status,
            "difference": self.difference,
            "threshold": self.threshold,
            "decided": self.decided,
        }


@dataclass(frozen=True, slots=True)
class ClientReport:
    components: tuple[ComponentNode, ...]
    routes: tuple[str, ...]
    gaps: tuple[PlatformGap, ...]
    accessibility: tuple[ClientFinding, ...]
    sensitive: tuple[ClientFinding, ...]
    visual: tuple[VisualCheck, ...]
    targets: tuple[Platform, ...]
    reasons: tuple[str, ...]

    @property
    def undecided_visual(self) -> tuple[VisualCheck, ...]:
        return tuple(item for item in self.visual if not item.decided)

    @property
    def failed_visual(self) -> tuple[VisualCheck, ...]:
        return tuple(item for item in self.visual if item.status == "fail")

    @property
    def allowed(self) -> bool:
        return (
            not self.gaps
            and not any(item.blocking for item in self.accessibility)
            and not self.sensitive
            and not self.undecided_visual
            and not self.failed_visual
        )

    @property
    def risk_class(self) -> RiskClass:
        if self.gaps or self.failed_visual:
            return RiskClass.R3
        if self.sensitive or self.undecided_visual:
            return RiskClass.R2
        return RiskClass.R1

    def to_payload(self) -> dict[str, Any]:
        return {
            "componentGraph": [item.to_payload() for item in self.components],
            "routes": list(self.routes),
            "platformCompatibilityMatrix": {
                "targets": [item.value for item in self.targets],
                "gaps": [item.to_payload() for item in self.gaps],
            },
            "accessibilityReport": [item.to_payload() for item in self.accessibility],
            "sensitiveSurfaces": [item.to_payload() for item in self.sensitive],
            "visualDiff": [item.to_payload() for item in self.visual],
            "allowed": self.allowed,
            "riskClass": self.risk_class.value,
            "reasons": list(self.reasons),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


def _framework_of(path: str, text: str) -> str:
    if path.endswith(".dart"):
        return "flutter"
    if path.endswith(".vue"):
        return "vue"
    if path.endswith((".wxml", ".wxss", ".axml")):
        return "miniprogram"
    if "defineComponent" in text or "from 'vue'" in text:
        return "vue"
    if "React" in text or _HOOK.search(text) or path.endswith((".jsx", ".tsx")):
        return "react"
    return "unknown"


def detect_capabilities(text: str) -> tuple[Capability, ...]:
    """Runtime capabilities a file actually reaches for."""

    found: list[Capability] = []
    for capability, patterns in _CAPABILITY_MARKERS.items():
        if any(pattern.search(text) for pattern in patterns):
            found.append(capability)
    return tuple(sorted(found, key=lambda item: item.value))


def build_component_graph(snapshot: WorkspaceSnapshot) -> tuple[ComponentNode, ...]:
    """Components, their framework, and what each one depends on at runtime."""

    nodes: list[ComponentNode] = []
    for record in snapshot:
        if not record.path.endswith(_CLIENT_EXTENSIONS):
            continue
        text = record.text
        if text is None:
            #: Unreadable client source is unscanned, not component-free.
            continue
        framework = _framework_of(record.path, text)
        capabilities = detect_capabilities(text)
        names = [
            match.group("js") or match.group("vue") or match.group("dart")
            for match in _COMPONENT.finditer(text)
        ]
        if not names:
            names = [record.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]]
        stateful = bool(
            _CLASS_COMPONENT.search(text)
            or re.search(r"\buseState\s*\(|\bthis\.state\b|StatefulWidget|reactive\s*\(", text)
        )
        for name in names:
            nodes.append(
                ComponentNode(
                    name=name,
                    path=record.path,
                    framework=framework,
                    stateful=stateful,
                    capabilities=capabilities,
                )
            )
    return tuple(sorted(nodes, key=lambda item: (item.path, item.name)))


def collect_routes(snapshot: WorkspaceSnapshot) -> tuple[str, ...]:
    routes: set[str] = set()
    for record in snapshot:
        text = record.text
        if text is None or not record.path.endswith(_CLIENT_EXTENSIONS):
            continue
        if not re.search(r"\brout(?:e|er|es)\b", text, re.IGNORECASE):
            continue
        for match in _ROUTE.finditer(text):
            candidate = match.group(1)
            if len(candidate) > 1 or candidate == "/":
                routes.add(candidate)
    return tuple(sorted(routes))


def platform_matrix(
    components: Sequence[ComponentNode],
    targets: Sequence[Platform],
) -> tuple[PlatformGap, ...]:
    """Every capability a component uses that a declared target cannot provide."""

    gaps: list[PlatformGap] = []
    for platform in targets:
        supported = PLATFORM_CAPABILITIES.get(platform, frozenset())
        for component in components:
            for capability in component.capabilities:
                if capability in supported:
                    continue
                gaps.append(
                    PlatformGap(
                        platform=platform,
                        capability=capability,
                        component=component.name,
                        path=component.path,
                        adapter=_adapter_for(capability, platform),
                    )
                )
    return tuple(gaps)


def _adapter_for(capability: Capability, platform: Platform) -> str:
    if capability is Capability.DOM:
        return (
            f"{platform.value} has no DOM; the component must be rewritten against the platform's "
            "own view layer, not shimmed"
        )
    if capability is Capability.DYNAMIC_IMPORT:
        return (
            f"{platform.value} forbids loading arbitrary code at runtime; the branches must be "
            "bundled statically and selected by configuration"
        )
    if capability is Capability.SERVICE_WORKER:
        return f"no service worker on {platform.value}; move caching behind an explicit storage layer"
    if capability is Capability.NATIVE_PAYMENT:
        return f"{platform.value} has no native payment surface; route to the host's payment API"
    if capability is Capability.BACKGROUND_TASK:
        return f"{platform.value} suspends background work; the task must be resumable from foreground"
    return f"provide a {capability.value} adapter for {platform.value}, or gate the feature off there"


def check_accessibility(snapshot: WorkspaceSnapshot, paths: Sequence[str]) -> tuple[ClientFinding, ...]:
    findings: list[ClientFinding] = []
    for path in sorted(set(paths)):
        record = snapshot.get(path)
        if record is None or record.text is None:
            continue
        for rule_id, pattern, message in _A11Y_CHECKS:
            for match in pattern.finditer(record.text):
                findings.append(
                    ClientFinding(
                        rule_id=rule_id,
                        path=path,
                        line=record.text.count("\n", 0, match.start()) + 1,
                        message=message,
                        blocking=rule_id != "positive-tabindex",
                    )
                )
    return tuple(findings)


def sensitive_surfaces(
    snapshot: WorkspaceSnapshot,
    patch: PatchSet,
) -> tuple[ClientFinding, ...]:
    """Touched code on a surface that fails silently rather than loudly."""

    findings: list[ClientFinding] = []
    for change in patch.changes:
        record = snapshot.get(change.path)
        if record is None or record.text is None:
            continue
        lines = record.text.splitlines()
        touched: set[int] = set()
        for hunk in change.hunks:
            for offset in range(hunk.after_start, hunk.after_start + max(1, hunk.after_length)):
                touched.add(offset)
        for number in sorted(touched):
            if not 1 <= number <= len(lines):
                continue
            line = lines[number - 1]
            for surface, pattern, message in _SENSITIVE_SURFACES:
                if pattern.search(line):
                    findings.append(
                        ClientFinding(
                            rule_id=f"sensitive-surface:{surface}",
                            path=change.path,
                            line=number,
                            message=f"{message}; this line was changed and needs its own verification",
                            blocking=True,
                        )
                    )
    #: One finding per surface per file: a hundred analytics lines in one file
    #: is one review item, not a hundred.
    unique: dict[tuple[str, str], ClientFinding] = {}
    for finding in findings:
        unique.setdefault((finding.path, finding.rule_id), finding)
    return tuple(sorted(unique.values(), key=lambda item: (item.path, item.rule_id)))


def analyse(
    snapshot: WorkspaceSnapshot,
    patch: PatchSet,
    *,
    targets: Sequence[Platform] = (Platform.WEB,),
    journeys: Sequence[str] = (),
    visual_results: Sequence[Mapping[str, Any]] = (),
) -> ClientReport:
    """The full client-side report for one change."""

    components = build_component_graph(snapshot)
    touched_paths = [change.path for change in patch.changes]
    touched_components = tuple(item for item in components if item.path in set(touched_paths))
    gaps = platform_matrix(touched_components or components, targets)
    accessibility = check_accessibility(snapshot, touched_paths)
    sensitive = sensitive_surfaces(snapshot, patch)

    supplied = {str(item.get("journey", "")): item for item in visual_results}
    checks: list[VisualCheck] = []
    for journey in journeys or tuple(f"route:{route}" for route in collect_routes(snapshot)[:10]):
        result = supplied.get(journey)
        if result is None:
            checks.append(VisualCheck(journey=journey))
        else:
            checks.append(
                VisualCheck(
                    journey=journey,
                    status=str(result.get("status", "not-run")),
                    difference=str(result.get("difference", "")),
                    threshold=str(result.get("threshold", "0.01")),
                )
            )

    reasons: list[str] = []
    undecided = [item for item in checks if not item.decided]
    if undecided:
        reasons.append(
            f"{len(undecided)} visual journey/journeys were not rendered; no renderer means the "
            "visual result is undecided, and undecided is not 'unchanged'"
        )
    for gap in gaps[:20]:
        reasons.append(
            f"{gap.component} uses {gap.capability.value}, which {gap.platform.value} does not "
            f"provide: {gap.adapter}"
        )
    for finding in sensitive[:20]:
        reasons.append(f"{finding.path}: {finding.message}")
    for finding in (item for item in accessibility if item.blocking):
        reasons.append(f"{finding.path}:{finding.line} {finding.rule_id}: {finding.message}")
    return ClientReport(
        components=components,
        routes=collect_routes(snapshot),
        gaps=gaps,
        accessibility=accessibility,
        sensitive=sensitive,
        visual=tuple(checks),
        targets=tuple(targets),
        reasons=tuple(reasons),
    )


__all__ = [
    "PLATFORM_CAPABILITIES",
    "Capability",
    "ClientFinding",
    "ClientReport",
    "ComponentNode",
    "Platform",
    "PlatformGap",
    "VisualCheck",
    "analyse",
    "build_component_graph",
    "check_accessibility",
    "collect_routes",
    "detect_capabilities",
    "platform_matrix",
    "sensitive_surfaces",
]
