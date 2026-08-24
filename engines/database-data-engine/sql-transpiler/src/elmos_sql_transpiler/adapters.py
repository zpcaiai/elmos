from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import version
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from sqlglot import exp
from sqlglot.errors import ErrorLevel

_SQLGLOT_VERSION = version("sqlglot")


def _digest_text(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _canonical_digest(value: Any) -> str:
    return _digest_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


@dataclass(frozen=True)
class AdapterRuleTrace:
    rule_id: str
    rule_version: str
    action: str
    input_digest: str
    output_digest: str
    rule_digest: str

    def to_dict(self) -> dict[str, str]:
        return {
            "ruleId": self.rule_id,
            "ruleVersion": self.rule_version,
            "action": self.action,
            "inputDigest": self.input_digest,
            "outputDigest": self.output_digest,
            "ruleDigest": self.rule_digest,
        }


@dataclass(frozen=True)
class AdapterEmission:
    sql: str
    adapter_id: str
    adapter_version: str
    protocol_version: str
    adapter_digest: str
    rules: tuple[AdapterRuleTrace, ...]


@runtime_checkable
class TargetAdapter(Protocol):
    """Exact-profile target renderer contract.

    Implementations own target emission. A compatibility label or a similar
    grammar is not enough to register an adapter: each registration is bound
    to one existing exact target profile and returns content-addressed trace.
    """

    @property
    def adapter_id(self) -> str: ...

    @property
    def adapter_version(self) -> str: ...

    @property
    def protocol_version(self) -> str: ...

    @property
    def target_profile_id(self) -> str: ...

    @property
    def target_dialect(self) -> str: ...

    @property
    def adapter_digest(self) -> str: ...

    def emit(self, expression: exp.Expression) -> AdapterEmission: ...


@dataclass(frozen=True)
class SqlglotTargetAdapter:
    adapter_id: str
    target_profile_id: str
    target_dialect: str
    adapter_version: str = "1.0.0"
    protocol_version: str = "1.0"

    @property
    def adapter_digest(self) -> str:
        return _canonical_digest(
            {
                "adapterId": self.adapter_id,
                "adapterVersion": self.adapter_version,
                "protocolVersion": self.protocol_version,
                "targetProfileId": self.target_profile_id,
                "targetDialect": self.target_dialect,
                "renderer": "sqlglot-expression.sql",
                "rendererVersion": _SQLGLOT_VERSION,
                "unsupportedLevel": "RAISE",
            }
        )

    def emit(self, expression: exp.Expression) -> AdapterEmission:
        input_digest = _canonical_digest(expression.dump())
        rendered = expression.sql(
            dialect=self.target_dialect,
            pretty=True,
            unsupported_level=ErrorLevel.RAISE,
        )
        output_digest = _digest_text(rendered)
        rule_id = "core.sqlglot-target-emitter"
        rule_version = "1.0.0"
        rule_digest = _canonical_digest(
            {
                "ruleId": rule_id,
                "ruleVersion": rule_version,
                "adapterDigest": self.adapter_digest,
                "targetDialect": self.target_dialect,
                "rendererVersion": _SQLGLOT_VERSION,
                "unsupportedLevel": "RAISE",
            }
        )
        return AdapterEmission(
            sql=rendered,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            protocol_version=self.protocol_version,
            adapter_digest=self.adapter_digest,
            rules=(
                AdapterRuleTrace(
                    rule_id=rule_id,
                    rule_version=rule_version,
                    action="EMIT_TARGET_SQL",
                    input_digest=input_digest,
                    output_digest=output_digest,
                    rule_digest=rule_digest,
                ),
            ),
        )


class TargetAdapterRegistry:
    def __init__(self, adapters: Sequence[TargetAdapter]) -> None:
        by_profile: dict[str, TargetAdapter] = {}
        by_id: dict[str, TargetAdapter] = {}
        for adapter in adapters:
            if not isinstance(adapter, TargetAdapter):
                raise TypeError("target adapter does not implement the protocol")
            if adapter.target_profile_id in by_profile:
                raise ValueError(f"duplicate target profile adapter: {adapter.target_profile_id}")
            if adapter.adapter_id in by_id:
                raise ValueError(f"duplicate target adapter id: {adapter.adapter_id}")
            by_profile[adapter.target_profile_id] = adapter
            by_id[adapter.adapter_id] = adapter
        self._by_profile = MappingProxyType(by_profile)
        self._by_id = MappingProxyType(by_id)

    def for_profile(self, profile_id: str) -> TargetAdapter:
        try:
            return self._by_profile[profile_id]
        except KeyError as error:
            raise ValueError(
                f"verified target adapter is unavailable for profile {profile_id}"
            ) from error

    def by_id(self, adapter_id: str) -> TargetAdapter | None:
        return self._by_id.get(adapter_id)

    def capabilities(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "adapterId": adapter.adapter_id,
                "adapterVersion": adapter.adapter_version,
                "protocolVersion": adapter.protocol_version,
                "targetProfileId": adapter.target_profile_id,
                "targetDialect": adapter.target_dialect,
                "rendererVersion": _SQLGLOT_VERSION,
                "adapterDigest": adapter.adapter_digest,
            }
            for adapter in sorted(
                self._by_profile.values(), key=lambda item: item.target_profile_id
            )
        )


_CORE_ADAPTERS = (
    SqlglotTargetAdapter(
        adapter_id="core.postgresql-17.5.sqlglot-target-adapter",
        target_profile_id="postgresql-17.5",
        target_dialect="postgres",
    ),
    SqlglotTargetAdapter(
        adapter_id="core.postgresql-18.4.sqlglot-target-adapter",
        target_profile_id="postgresql-18.4",
        target_dialect="postgres",
    ),
    SqlglotTargetAdapter(
        adapter_id="core.mysql-8.4.10-lts.sqlglot-target-adapter",
        target_profile_id="mysql-8.4.10-lts",
        target_dialect="mysql",
    ),
    SqlglotTargetAdapter(
        adapter_id="core.sqlserver-2022-cu26.sqlglot-target-adapter",
        target_profile_id="sqlserver-2022-cu26",
        target_dialect="tsql",
    ),
    SqlglotTargetAdapter(
        adapter_id="core.oracle-26ai-ee.sqlglot-target-adapter",
        target_profile_id="oracle-26ai-ee",
        target_dialect="oracle",
    ),
    SqlglotTargetAdapter(
        adapter_id="core.sqlite-3.53.3.sqlglot-target-adapter",
        target_profile_id="sqlite-3.53.3",
        target_dialect="sqlite",
    ),
    SqlglotTargetAdapter(
        adapter_id="core.duckdb-1.5.4.sqlglot-target-adapter",
        target_profile_id="duckdb-1.5.4",
        target_dialect="duckdb",
    ),
)

TARGET_ADAPTERS = TargetAdapterRegistry(_CORE_ADAPTERS)


def target_adapter_for_profile(profile_id: str) -> TargetAdapter:
    return TARGET_ADAPTERS.for_profile(profile_id)


def target_adapter_by_id(adapter_id: str) -> TargetAdapter | None:
    return TARGET_ADAPTERS.by_id(adapter_id)


def target_adapter_capabilities() -> tuple[dict[str, str], ...]:
    return TARGET_ADAPTERS.capabilities()
