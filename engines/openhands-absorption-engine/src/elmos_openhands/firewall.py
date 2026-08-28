"""Policy Decision Point for every tool action."""

from __future__ import annotations

import json
import re
import shlex
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .models import Action, Identity, PolicyDecision, RiskLevel, new_id


@dataclass(frozen=True, slots=True)
class FirewallContext:
    identity: Identity
    allowed_capabilities: frozenset[str] = frozenset()
    allowed_roots: tuple[str, ...] = ()
    allowed_domains: frozenset[str] = frozenset()
    secret_values: tuple[str, ...] = ()
    policy_version: str = "openhands-policy-v1"
    require_approval_at: RiskLevel = RiskLevel.R4
    package_name: str | None = None


@dataclass(frozen=True, slots=True)
class FirewallResult:
    decision: PolicyDecision
    normalized_args: dict[str, Any]


class ActionFirewall:
    """A conservative deterministic PDP.

    The firewall never executes actions and never derives tenant context from
    action input. Its result is suitable for persistence in the event ledger.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._disabled_tools: set[str] = set()
        self._disabled_tenants: set[str] = set()
        self._disabled_packages: set[str] = set()

    def kill_tool(self, tool: str) -> None:
        with self._lock:
            self._disabled_tools.add(tool)

    def enable_tool(self, tool: str) -> None:
        with self._lock:
            self._disabled_tools.discard(tool)

    def kill_tenant(self, tenant_id: str) -> None:
        with self._lock:
            self._disabled_tenants.add(tenant_id)

    def enable_tenant(self, tenant_id: str) -> None:
        with self._lock:
            self._disabled_tenants.discard(tenant_id)

    def kill_package(self, package_name: str) -> None:
        with self._lock:
            self._disabled_packages.add(package_name)

    def decide(self, action: Action, context: FirewallContext, *, approved_by: str | None = None) -> FirewallResult:
        if action.risk_hint is not None:
            risk = action.risk_hint
        else:
            risk = self.classify(action)
        reasons: list[str] = []
        rules: list[str] = ["schema_validation", "tenant_rbac", "capability_grant"]
        normalized = json.loads(json.dumps(dict(action.args), default=str))

        with self._lock:
            disabled = (
                action.tool in self._disabled_tools
                or context.identity.tenant_id in self._disabled_tenants
                or (context.package_name is not None and context.package_name in self._disabled_packages)
            )
        if disabled:
            reasons.append("KILL_SWITCH_ACTIVE")
            return self._result("deny", risk, rules + ["kill_switch"], reasons, context, approved_by, normalized)

        missing = sorted(set(action.required_capabilities) - set(context.allowed_capabilities))
        if missing:
            reasons.append("CAPABILITY_NOT_GRANTED:" + ",".join(missing))
        if self._path_violation(action, context):
            rules.append("path_policy")
            reasons.append("PATH_OUTSIDE_SCOPE")
        if self._network_violation(action, context):
            rules.append("network_egress_policy")
            reasons.append("NETWORK_EGRESS_NOT_ALLOWLISTED")
        if self._secret_violation(action, context):
            rules.append("secret_taint_check")
            reasons.append("RAW_SECRET_IN_ACTION")
        if self._prompt_injection(action):
            rules.append("prompt_injection_classifier")
            reasons.append("PROMPT_INJECTION_SIGNAL")
        if self._destructive_violation(action):
            rules.extend(["destructive_command_guard", "data_exfiltration_guard"])
            reasons.append("DESTRUCTIVE_OR_EXFILTRATION_COMMAND")

        if reasons:
            return self._result("deny", risk, rules, reasons, context, approved_by, normalized)
        if risk.value >= context.require_approval_at.value:
            if approved_by:
                reasons.append("SCOPED_HUMAN_APPROVAL")
                return self._result("allow", risk, rules + ["human_approval"], reasons, context, approved_by, normalized)
            return self._result("require_approval", risk, rules + ["human_approval"], ["RISK_REQUIRES_APPROVAL"], context, approved_by, normalized)
        return self._result("allow", risk, rules, ["POLICY_ALLOW"], context, approved_by, normalized)

    @staticmethod
    def classify(action: Action) -> RiskLevel:
        tool = action.tool.lower()
        operation = str(action.args.get("operation", "")).lower()
        if tool.startswith("browser") or tool.startswith("cloud") or "network" in tool:
            return RiskLevel.R4 if operation in {"navigate", "request", "mutate"} else RiskLevel.R3
        if tool.startswith("git") and operation in {"push", "force_push", "merge", "delete_branch"}:
            return RiskLevel.R4
        if tool.startswith("database") or operation in {"drop", "truncate", "rotate_secret"}:
            return RiskLevel.R6
        if tool.startswith("shell"):
            return RiskLevel.R2
        if tool.startswith("filesystem"):
            return RiskLevel.R1 if operation in {"write", "delete", "move"} else RiskLevel.R0
        return RiskLevel.R2

    def _path_violation(self, action: Action, context: FirewallContext) -> bool:
        paths = list(action.read_scope) + list(action.write_scope) + list(_path_values(action.args))
        if not context.allowed_roots:
            # A caller cannot turn an unscoped action into an authorized path
            # operation by omitting the explicit read/write scope fields.
            return bool(paths)
        roots = tuple(Path(root).resolve() for root in context.allowed_roots)
        for raw in paths:
            try:
                path = Path(raw)
                if ".." in path.parts:
                    return True
                if path.is_absolute():
                    inside = any(path.resolve().is_relative_to(root) for root in roots)
                else:
                    inside = any((root / path).resolve().is_relative_to(root) for root in roots)
                if not inside:
                    return True
            except (OSError, RuntimeError, ValueError):
                return True
        return False

    @staticmethod
    def _network_violation(action: Action, context: FirewallContext) -> bool:
        urls = list(_url_values(action.args))
        if not urls:
            return False
        allowed = {domain.lower() for domain in context.allowed_domains}
        if not allowed:
            return True
        return any((urlparse(url).hostname or "").lower() not in allowed for url in urls)

    @staticmethod
    def _secret_violation(action: Action, context: FirewallContext) -> bool:
        if not context.secret_values:
            return False
        serialized = json.dumps(action.args, ensure_ascii=False, default=str)
        return any(secret and secret in serialized for secret in context.secret_values)

    @staticmethod
    def _prompt_injection(action: Action) -> bool:
        serialized = json.dumps(action.args, ensure_ascii=False, default=str).lower()
        return any(
            marker in serialized
            for marker in (
                "ignore previous instructions",
                "ignore all prior instructions",
                "system prompt",
                "reveal the secret",
                "disable the firewall",
                "bypass policy",
            )
        )

    @staticmethod
    def _destructive_violation(action: Action) -> bool:
        command = action.args.get("command") or action.args.get("cmd")
        if isinstance(command, list):
            tokens = [str(token).lower() for token in command]
        elif isinstance(command, str):
            try:
                tokens = [token.lower() for token in shlex.split(command)]
            except ValueError:
                return True
        else:
            tokens = []
        compact = " ".join(tokens)
        patterns = (
            r"(^|\s)rm\s+-[a-z]*r[a-z]*f",
            r"(^|\s)git\s+reset\s+--hard",
            r"(^|\s)git\s+push\b.*(?:--force(?:-with-lease)?|-f)(?:\s|$)",
            r"force[-_ ]push",
            r"\bdrop\s+(database|table|schema)\b",
            r"\btruncate\s+table\b",
            r"\bcurl\b.*\b(token|secret|password|credential)\b",
            r"\bnc\b|\bnetcat\b",
        )
        return any(re.search(pattern, compact) for pattern in patterns)

    @staticmethod
    def _result(decision: str, risk: RiskLevel, rules: list[str], reasons: list[str], context: FirewallContext, approved_by: str | None, normalized: dict[str, Any]) -> FirewallResult:
        return FirewallResult(PolicyDecision(new_id(), decision, risk, tuple(dict.fromkeys(rules)), tuple(reasons), context.policy_version, approved_by), normalized)


def _path_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "paths", "cwd", "working_directory", "source", "destination", "file"}:
                if isinstance(item, str):
                    yield item
                elif isinstance(item, list):
                    yield from (str(entry) for entry in item)
            yield from _path_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _path_values(item)


def _url_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _url_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _url_values(item)
    elif isinstance(value, str) and urlparse(value).scheme in {"http", "https", "ftp"}:
        yield value
