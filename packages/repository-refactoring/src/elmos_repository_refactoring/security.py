"""Skill 19 — the security controls a refactor must not quietly weaken.

This module compares the *before* and *after* of a change along the axes that
a refactor most often erodes by accident: an authorisation decorator dropped
while moving a function, a validator lost when two handlers merged, an
exception handler widened until it swallows a denial, a permission opened to
get a test passing, a dependency pinned down to an older version.

Two rules keep the output honest:

* **A removed control is a finding even when nothing replaced it visibly.**
  Losing ``@requires_role`` is reported whether or not a new check appears
  elsewhere; proving the replacement is equivalent is a human's job, and the
  finding is what puts it in front of one.
* **A suppression is a finding until it carries an approval and an expiry.**
  ``# noqa``, ``# nosec``, ``eslint-disable`` and friends are how a scanner
  gets quiet without the code getting safer, so an added suppression is
  reported with the rule it silences.

Scanners themselves are executed work.  With no executor the scan section is
``not-run`` — never ``clean`` — and :func:`decide` treats that as blocking.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from . import sarif
from .contracts import RiskClass, sha256_payload, sha256_text
from .patch import PatchSet
from .sandbox import ExecutionStatus
from .workspace import WorkspaceSnapshot


class ControlKind(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    TENANT_BOUNDARY = "tenant-boundary"
    INPUT_VALIDATION = "input-validation"
    CRYPTOGRAPHY = "cryptography"
    SECRET_HANDLING = "secret-handling"  # noqa: S105 — a control name, not a credential
    LOGGING = "logging"
    DATA_EXPOSURE = "data-exposure"
    SUPPLY_CHAIN = "supply-chain"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOTE = "note"


_SARIF_LEVEL = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.NOTE: "note",
}

BLOCKING_SEVERITIES = frozenset({Severity.CRITICAL, Severity.HIGH})


#: Markers whose *disappearance* from a file is a control removal.  Each entry
#: is (regex, control kind, severity, human explanation).
_CONTROL_MARKERS: tuple[tuple[re.Pattern[str], ControlKind, Severity, str], ...] = (
    (
        re.compile(r"@(?:login_required|authenticated|requires_auth|Authenticated)\b"),
        ControlKind.AUTHENTICATION,
        Severity.CRITICAL,
        "an authentication requirement was removed from this file",
    ),
    (
        re.compile(r"@(?:requires_role|require_permission|has_permission|PreAuthorize|RolesAllowed)\b"),
        ControlKind.AUTHORIZATION,
        Severity.CRITICAL,
        "an authorisation check was removed from this file",
    ),
    (
        re.compile(r"\b(?:tenant_id|organization_id|account_id)\s*==|filter_by_tenant|scope_to_tenant\b"),
        ControlKind.TENANT_BOUNDARY,
        Severity.CRITICAL,
        "a tenant-scoping predicate was removed; cross-tenant reads become possible",
    ),
    (
        re.compile(r"\b(?:validate|is_valid|schema\.load|parse_obj|model_validate|@Valid)\b"),
        ControlKind.INPUT_VALIDATION,
        Severity.HIGH,
        "an input validation step was removed from this file",
    ),
    (
        re.compile(r"\b(?:verify_signature|hmac\.compare_digest|constant_time_compare|check_password)\b"),
        ControlKind.CRYPTOGRAPHY,
        Severity.CRITICAL,
        "a signature or password verification was removed",
    ),
    (
        re.compile(r"\b(?:redact|mask|scrub|sanitize)\w*\s*\("),
        ControlKind.LOGGING,
        Severity.HIGH,
        "a redaction step was removed; the value it protected may now reach a log",
    ),
)

#: Patterns whose *appearance* is itself a weakening.
_WEAKENING_PATTERNS: tuple[tuple[str, re.Pattern[str], ControlKind, Severity, str], ...] = (
    (
        "tls-verification-disabled",
        re.compile(r"verify\s*=\s*False|InsecureSkipVerify\s*:\s*true|rejectUnauthorized\s*:\s*false", re.IGNORECASE),
        ControlKind.CRYPTOGRAPHY,
        Severity.CRITICAL,
        "certificate verification disabled: the connection is no longer authenticated",
    ),
    (
        "weak-hash",
        re.compile(r"\b(?:md5|sha1)\s*\(", re.IGNORECASE),
        ControlKind.CRYPTOGRAPHY,
        Severity.HIGH,
        "a broken hash function is used; if this guards anything, it does not",
    ),
    (
        "dynamic-evaluation",
        re.compile(r"\b(?:eval|exec)\s*\(|new\s+Function\s*\(", re.IGNORECASE),
        ControlKind.INPUT_VALIDATION,
        Severity.HIGH,
        "dynamic evaluation of a string; any input reaching it is code",
    ),
    (
        "shell-injection-surface",
        re.compile(r"shell\s*=\s*True|os\.system\s*\(|child_process\.exec\s*\("),
        ControlKind.INPUT_VALIDATION,
        Severity.HIGH,
        "a shell is spawned from a composed string",
    ),
    (
        "wide-permission",
        re.compile(r"chmod\s+(?:0?777|a\+rwx)|\"Effect\"\s*:\s*\"Allow\"[^}]*\"Action\"\s*:\s*\"\*\"|AllowAll"),
        ControlKind.AUTHORIZATION,
        Severity.CRITICAL,
        "a permission was widened to everything",
    ),
    (
        "swallowed-exception",
        re.compile(r"except\s+\w*\s*:?\s*(?:#.*)?$\s*\n\s*(?:pass|return\s+True)", re.MULTILINE),
        ControlKind.AUTHORIZATION,
        Severity.HIGH,
        "an exception is swallowed; a denial raised inside this block becomes a success",
    ),
    (
        "cors-wildcard",
        re.compile(r"Access-Control-Allow-Origin[\"']?\s*[:=]\s*[\"']\*|allow_origins\s*=\s*\[\s*[\"']\*"),
        ControlKind.DATA_EXPOSURE,
        Severity.HIGH,
        "any origin may read responses from this endpoint",
    ),
    (
        "debug-enabled",
        re.compile(r"\bDEBUG\s*=\s*True\b|app\.run\([^)]*debug\s*=\s*True"),
        ControlKind.DATA_EXPOSURE,
        Severity.MEDIUM,
        "debug mode exposes stack traces and internals to callers",
    ),
)

#: A literal that looks like a credential.  Deliberately narrow: the model
#: never reads secret *values*, only reports the location.
_SECRET_ASSIGNMENT = re.compile(
    r"(?P<name>\b\w*(?:secret|token|password|passwd|api[_-]?key|private[_-]?key|credential)\w*)\s*"
    r"[=:]\s*[\"'](?P<value>[^\"'\n]{8,})[\"']",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(
    r"^(?:x{3,}|\*{3,}|\$\{[^}]+\}|<[^>]+>|changeme|placeholder|example|dummy|test|none|null|"
    r"process\.env\..*|os\.environ.*)$",
    re.IGNORECASE,
)

_SUPPRESSION = re.compile(
    r"#\s*(?:noqa|nosec|type:\s*ignore|pylint:\s*disable)(?:[:\s]\s*(?P<rule>[\w,\-\[\]]+))?"
    r"|//\s*eslint-disable(?:-next-line)?\s*(?P<eslint>[\w@/\-]*)"
    r"|@SuppressWarnings\s*\(\s*[\"'](?P<java>[^\"']+)"
)
_APPROVAL = re.compile(r"\b(?:approved-by|owner)\s*[:=]\s*\S+", re.IGNORECASE)
_EXPIRY = re.compile(r"\b(?:expires|until|review-by)\s*[:=]\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    rule_id: str
    control: ControlKind
    severity: Severity
    path: str
    line: int
    message: str
    #: Present when the finding is a *removal*: what used to be there.
    removed_text: str = ""

    @property
    def blocking(self) -> bool:
        return self.severity in BLOCKING_SEVERITIES

    def to_payload(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "control": self.control.value,
            "severity": self.severity.value,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "removedText": self.removed_text,
            "blocking": self.blocking,
        }

    def to_sarif(self) -> sarif.SarifResult:
        return sarif.SarifResult(
            rule_id=self.rule_id,
            level=_SARIF_LEVEL[self.severity],
            message=self.message,
            path=self.path,
            start_line=self.line,
            properties={"control": self.control.value, "severity": self.severity.value},
        )


@dataclass(frozen=True, slots=True)
class SuppressionFinding:
    path: str
    line: int
    marker: str
    rule: str
    approved: bool
    expires: str

    @property
    def acceptable(self) -> bool:
        return self.approved and bool(self.expires)

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "marker": self.marker,
            "rule": self.rule or "unspecified",
            "approved": self.approved,
            "expires": self.expires,
            "acceptable": self.acceptable,
        }


def _version_key(value: str) -> tuple[int, ...]:
    """Numeric prefix of a version, for ordering only.

    Deliberately crude: it answers "is this smaller" for the common
    ``major.minor.patch`` case and returns an empty tuple for anything it
    cannot order, which :meth:`DependencyChange.downgraded` treats as
    *unknown* rather than as "not a downgrade".
    """

    parts = re.findall(r"\d+", value.split("+", 1)[0])
    return tuple(int(item) for item in parts[:4])


@dataclass(frozen=True, slots=True)
class DependencyChange:
    name: str
    before: str
    after: str
    ecosystem: str

    @property
    def kind(self) -> str:
        if not self.before:
            return "added"
        if not self.after:
            return "removed"
        return "changed"

    @property
    def downgraded(self) -> bool | None:
        """True when the version moved backwards, None when it cannot be ordered.

        A pin moving backwards is how a patched CVE comes back, so it is
        reported in its own right rather than folded into "changed".
        """

        if self.kind != "changed":
            return False
        left, right = _version_key(self.before), _version_key(self.after)
        if not left or not right:
            return None
        return right < left

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "before": self.before,
            "after": self.after,
            "ecosystem": self.ecosystem,
            "change": self.kind,
            "downgraded": self.downgraded,
        }


@dataclass(frozen=True, slots=True)
class SecurityReport:
    findings: tuple[SecurityFinding, ...]
    suppressions: tuple[SuppressionFinding, ...]
    sbom_delta: tuple[DependencyChange, ...]
    scan_status: str
    scan_runs: tuple[sarif.SarifRun, ...]
    threat_model_delta: tuple[Mapping[str, Any], ...]
    reasons: tuple[str, ...]

    @property
    def blocking(self) -> tuple[SecurityFinding, ...]:
        return tuple(item for item in self.findings if item.blocking)

    @property
    def unapproved_suppressions(self) -> tuple[SuppressionFinding, ...]:
        return tuple(item for item in self.suppressions if not item.acceptable)

    @property
    def allowed(self) -> bool:
        return (
            not self.blocking
            and not self.unapproved_suppressions
            and self.scan_status == ExecutionStatus.COMPLETED.value
        )

    @property
    def risk_class(self) -> RiskClass:
        if any(item.severity is Severity.CRITICAL for item in self.findings):
            return RiskClass.R4
        if self.blocking or self.unapproved_suppressions:
            return RiskClass.R3
        return RiskClass.R2

    def sarif_log(self) -> dict[str, Any]:
        rules = tuple(
            sarif.SarifRule(
                id=rule_id,
                name=rule_id,
                short_description=next(
                    item.message for item in self.findings if item.rule_id == rule_id
                ),
                default_level=_SARIF_LEVEL[
                    max(
                        (item.severity for item in self.findings if item.rule_id == rule_id),
                        key=lambda value: list(Severity).index(value),
                    )
                ],
            )
            for rule_id in sorted({item.rule_id for item in self.findings})
        )
        own = sarif.SarifRun(
            tool_name="elmos-security-preservation",
            tool_version="1.0.0",
            rules=rules,
            results=tuple(item.to_sarif() for item in self.findings),
            invocation_successful=True,
            properties={"scanStatus": self.scan_status},
        )
        return sarif.build_log((own, *self.scan_runs))

    def to_payload(self) -> dict[str, Any]:
        return {
            "securityDiff": [item.to_payload() for item in self.findings],
            "suppressions": [item.to_payload() for item in self.suppressions],
            "sbomDelta": [item.to_payload() for item in self.sbom_delta],
            "threatModelDelta": [dict(item) for item in self.threat_model_delta],
            "scanStatus": self.scan_status,
            "allowed": self.allowed,
            "riskClass": self.risk_class.value,
            "reasons": list(self.reasons),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def scan_text(path: str, text: str) -> tuple[SecurityFinding, ...]:
    """Weakening patterns present in one file's contents."""

    findings: list[SecurityFinding] = []
    for rule_id, pattern, control, severity, message in _WEAKENING_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                SecurityFinding(
                    rule_id=rule_id,
                    control=control,
                    severity=severity,
                    path=path,
                    line=line,
                    message=message,
                )
            )
    findings.extend(find_secrets(path, text))
    return tuple(findings)


def find_secrets(path: str, text: str) -> tuple[SecurityFinding, ...]:
    """Credential-shaped literals, reported by location and digest only.

    The matched value never appears in the finding.  A digest is included so
    two occurrences of the same secret can be correlated across files without
    the value itself entering an evidence bundle or a log.
    """

    findings: list[SecurityFinding] = []
    for match in _SECRET_ASSIGNMENT.finditer(text):
        value = match.group("value")
        if _PLACEHOLDER.match(value.strip()):
            continue
        if len(set(value)) < 5:
            continue
        line = text.count("\n", 0, match.start()) + 1
        findings.append(
            SecurityFinding(
                rule_id="hardcoded-credential",
                control=ControlKind.SECRET_HANDLING,
                severity=Severity.CRITICAL,
                path=path,
                line=line,
                message=(
                    f"'{match.group('name')}' is assigned a literal that looks like a credential "
                    f"(value withheld; digest {sha256_text(value)[7:19]})"
                ),
            )
        )
    return tuple(findings)


def find_suppressions(path: str, text: str) -> tuple[SuppressionFinding, ...]:
    """Every scanner-silencing marker, with whatever justification accompanies it."""

    found: list[SuppressionFinding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _SUPPRESSION.search(line)
        if match is None:
            continue
        rule = match.group("rule") or match.group("eslint") or match.group("java") or ""
        expiry = _EXPIRY.search(line)
        found.append(
            SuppressionFinding(
                path=path,
                line=number,
                marker=match.group(0).strip(),
                rule=rule.strip(),
                approved=bool(_APPROVAL.search(line)),
                expires=expiry.group(1) if expiry else "",
            )
        )
    return tuple(found)


def diff_controls(
    before: WorkspaceSnapshot,
    after: WorkspaceSnapshot,
    *,
    paths: Sequence[str] | None = None,
) -> tuple[SecurityFinding, ...]:
    """Controls that were present before the change and are absent after it."""

    candidates = list(paths) if paths is not None else [record.path for record in before]
    findings: list[SecurityFinding] = []
    for path in sorted(set(candidates)):
        old = before.get(path)
        new = after.get(path)
        if old is None or old.text is None:
            continue
        old_text = old.text
        new_text = "" if new is None or new.text is None else new.text
        if new is not None and new.text is None:
            #: The candidate file cannot be decoded.  We cannot claim the
            #: control survived, and we must not claim it was removed either.
            findings.append(
                SecurityFinding(
                    rule_id="control-unverifiable",
                    control=ControlKind.LOGGING,
                    severity=Severity.HIGH,
                    path=path,
                    line=1,
                    message=(
                        "the candidate version of this file could not be decoded, so no control "
                        "in it could be re-checked; unreadable is not unchanged"
                    ),
                )
            )
            continue
        for pattern, control, severity, message in _CONTROL_MARKERS:
            before_hits = pattern.findall(old_text)
            after_hits = pattern.findall(new_text)
            if len(before_hits) <= len(after_hits):
                continue
            line = 1
            for number, text_line in enumerate(old_text.splitlines(), start=1):
                if pattern.search(text_line):
                    line = number
                    break
            findings.append(
                SecurityFinding(
                    rule_id=f"control-removed:{control.value}",
                    control=control,
                    severity=severity,
                    path=path,
                    line=line,
                    message=(
                        f"{message} ({len(before_hits)} occurrence(s) before, "
                        f"{len(after_hits)} after)"
                    ),
                    removed_text=pattern.pattern,
                )
            )
    return tuple(findings)


def sbom_delta(
    before: Mapping[str, Mapping[str, str]],
    after: Mapping[str, Mapping[str, str]],
) -> tuple[DependencyChange, ...]:
    """Dependency additions, removals and version moves, per ecosystem."""

    changes: list[DependencyChange] = []
    for ecosystem in sorted(set(before) | set(after)):
        left = before.get(ecosystem, {})
        right = after.get(ecosystem, {})
        for name in sorted(set(left) | set(right)):
            old, new = left.get(name, ""), right.get(name, "")
            if old != new:
                changes.append(
                    DependencyChange(name=name, before=old, after=new, ecosystem=ecosystem)
                )
    return tuple(changes)


def threat_model_delta(
    findings: Sequence[SecurityFinding],
    dependencies: Sequence[DependencyChange],
) -> tuple[Mapping[str, Any], ...]:
    """What changed about the attack surface, grouped by the control it touches."""

    grouped: dict[ControlKind, list[SecurityFinding]] = {}
    for item in findings:
        grouped.setdefault(item.control, []).append(item)
    rows: list[Mapping[str, Any]] = []
    for control, items in sorted(grouped.items(), key=lambda entry: entry[0].value):
        rows.append(
            {
                "control": control.value,
                "findingCount": len(items),
                "worstSeverity": min(items, key=lambda item: list(Severity).index(item.severity)).severity.value,
                "paths": sorted({item.path for item in items})[:10],
                "requiresNegativeTest": control
                in (ControlKind.AUTHORIZATION, ControlKind.AUTHENTICATION, ControlKind.TENANT_BOUNDARY),
            }
        )
    downgrades = [item for item in dependencies if item.downgraded is not False]
    if downgrades:
        rows.append(
            {
                "control": ControlKind.SUPPLY_CHAIN.value,
                "findingCount": len(downgrades),
                "worstSeverity": Severity.HIGH.value,
                "paths": [],
                "requiresNegativeTest": False,
                "detail": (
                    "dependency pin(s) moved backwards or to an unorderable version: "
                    + ", ".join(
                        f"{item.name} {item.before} -> {item.after}" for item in sorted(
                            downgrades, key=lambda entry: entry.name
                        )[:10]
                    )
                    + "; a version going backwards can reinstate a fixed vulnerability"
                ),
            }
        )
    added = [item for item in dependencies if item.kind == "added"]
    if added:
        rows.append(
            {
                "control": ControlKind.SUPPLY_CHAIN.value,
                "findingCount": len(added),
                "worstSeverity": Severity.MEDIUM.value,
                "paths": [],
                "requiresNegativeTest": False,
                "detail": (
                    f"{len(added)} new dependency/dependencies enter the trust boundary: "
                    + ", ".join(sorted(item.name for item in added)[:10])
                ),
            }
        )
    return tuple(rows)


def negative_tests(findings: Sequence[SecurityFinding]) -> tuple[Mapping[str, str], ...]:
    """The abuse cases a reviewer should demand for each privilege finding."""

    cases: list[Mapping[str, str]] = []
    for item in findings:
        if item.control is ControlKind.AUTHORIZATION:
            cases.append(
                {
                    "name": f"denied-without-role:{item.path}:{item.line}",
                    "given": "a caller lacking the required role",
                    "expect": "the request is refused before any state is read or written",
                }
            )
        elif item.control is ControlKind.AUTHENTICATION:
            cases.append(
                {
                    "name": f"denied-anonymous:{item.path}:{item.line}",
                    "given": "an unauthenticated caller",
                    "expect": "the request is refused with no resource-specific detail in the error",
                }
            )
        elif item.control is ControlKind.TENANT_BOUNDARY:
            cases.append(
                {
                    "name": f"cross-tenant-denied:{item.path}:{item.line}",
                    "given": "a caller from tenant A requesting a resource owned by tenant B",
                    "expect": "the response is indistinguishable from the resource not existing",
                }
            )
    return tuple(cases)


# ---------------------------------------------------------------------------
# Adjudication
# ---------------------------------------------------------------------------


def analyse(
    before: WorkspaceSnapshot,
    after: WorkspaceSnapshot,
    patch: PatchSet,
    *,
    dependencies_before: Mapping[str, Mapping[str, str]] | None = None,
    dependencies_after: Mapping[str, Mapping[str, str]] | None = None,
    scanner_runs: Sequence[sarif.SarifRun] = (),
    scan_status: ExecutionStatus = ExecutionStatus.NOT_RUN,
) -> SecurityReport:
    """The full before/after security comparison for one change."""

    touched = sorted({change.path for change in patch.changes})
    findings: list[SecurityFinding] = list(diff_controls(before, after, paths=touched))
    suppressions: list[SuppressionFinding] = []
    for path in touched:
        record = after.get(path)
        if record is None:
            continue
        if record.text is None:
            findings.append(
                SecurityFinding(
                    rule_id="candidate-unreadable",
                    control=ControlKind.DATA_EXPOSURE,
                    severity=Severity.HIGH,
                    path=path,
                    line=1,
                    message="the changed file could not be decoded, so it could not be scanned",
                )
            )
            continue
        before_record = before.get(path)
        before_text = "" if before_record is None or before_record.text is None else before_record.text
        existing = {(item.rule_id, item.line) for item in scan_text(path, before_text)}
        for finding in scan_text(path, record.text):
            #: Only *newly introduced* weaknesses belong to this change.  A
            #: pre-existing one is reported by the baseline scan, not blamed
            #: on a refactor that merely moved it.
            if (finding.rule_id, finding.line) in existing:
                continue
            findings.append(finding)
        before_suppressions = {
            (item.marker, item.rule) for item in find_suppressions(path, before_text)
        }
        for item in find_suppressions(path, record.text):
            if (item.marker, item.rule) in before_suppressions:
                continue
            suppressions.append(item)

    for run in scanner_runs:
        for result in run.results:
            if result.level not in ("error", "warning"):
                continue
            findings.append(
                SecurityFinding(
                    rule_id=f"{run.tool_name}:{result.rule_id}",
                    control=ControlKind.SUPPLY_CHAIN,
                    severity=Severity.HIGH if result.level == "error" else Severity.MEDIUM,
                    path=result.path,
                    line=result.start_line,
                    message=result.message,
                )
            )

    delta = sbom_delta(dependencies_before or {}, dependencies_after or {})
    reasons: list[str] = []
    status = scan_status.value
    if scan_status is not ExecutionStatus.COMPLETED:
        reasons.append(
            f"the security scanners are '{status}'; an unexecuted scan is undecided, and this gate "
            "treats undecided as failing"
        )
    for dependency in delta:
        if dependency.downgraded is True:
            reasons.append(
                f"dependency '{dependency.name}' moved backwards from {dependency.before} to "
                f"{dependency.after}; a downgrade needs the same scrutiny as an upgrade, in the "
                "other direction"
            )
        elif dependency.downgraded is None:
            reasons.append(
                f"dependency '{dependency.name}' changed from '{dependency.before}' to "
                f"'{dependency.after}', which cannot be ordered; direction of the move is UNKNOWN"
            )
    for finding in sorted(
        (entry for entry in findings if entry.blocking),
        key=lambda entry: (entry.path, entry.line),
    )[:25]:
        reasons.append(
            f"{finding.severity.value} {finding.rule_id} at {finding.path}:{finding.line}: {finding.message}"
        )
    for suppression in sorted(
        (entry for entry in suppressions if not entry.acceptable),
        key=lambda entry: (entry.path, entry.line),
    )[:25]:
        missing = "approval" if not suppression.approved else "expiry"
        reasons.append(
            f"suppression '{suppression.marker}' at {suppression.path}:{suppression.line} has no "
            f"{missing}; a suppression without an owner and an end date is a permanent hole"
        )
    return SecurityReport(
        findings=tuple(sorted(findings, key=lambda item: (item.path, item.line, item.rule_id))),
        suppressions=tuple(sorted(suppressions, key=lambda item: (item.path, item.line))),
        sbom_delta=delta,
        scan_status=status,
        scan_runs=tuple(scanner_runs),
        threat_model_delta=threat_model_delta(findings, delta),
        reasons=tuple(reasons),
    )


__all__ = [
    "BLOCKING_SEVERITIES",
    "ControlKind",
    "DependencyChange",
    "SecurityFinding",
    "SecurityReport",
    "Severity",
    "SuppressionFinding",
    "analyse",
    "diff_controls",
    "find_secrets",
    "find_suppressions",
    "negative_tests",
    "sbom_delta",
    "scan_text",
    "threat_model_delta",
]
