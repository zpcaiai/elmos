"""Local ChinaDB query adapters bound to explicit compatibility modes.

Each of the 13 commercial targets owns a unique adapter identity.  A
compatibility label is never treated as a silent alias of PostgreSQL / MySQL /
Oracle: emission only proceeds when the request names a mode from that
target's allow-list, and the renderer is the typed sqlglot dialect for that
mode.  External execution, result equivalence and certification remain
``NOT_RUN`` / ``NOT_CERTIFIED``.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from sqlglot import exp
from sqlglot.errors import ErrorLevel

from .adapters import AdapterEmission, AdapterRuleTrace, _SQLGLOT_VERSION, _canonical_digest, _digest_text

_ORACLE = MappingProxyType(
    {
        "oracle-compatible-explicit": "oracle",
        "oracle-compatible": "oracle",
    }
)
_POSTGRES = MappingProxyType(
    {
        "pg-compatible-explicit": "postgres",
        "postgresql-compatible": "postgres",
        "a-compatible": "postgres",
    }
)
_MYSQL = MappingProxyType(
    {
        "mysql-compatible-explicit": "mysql",
        "mysql": "mysql",
    }
)
_KINGBASE = MappingProxyType({**_POSTGRES, **_ORACLE})
_GAUSSDB_M = MappingProxyType({**_MYSQL, **_POSTGRES})
_GBASE_8S = MappingProxyType(
    {
        **_ORACLE,
        "informix-compatible-explicit": "oracle",
    }
)


@dataclass(frozen=True)
class ChinaDbLocalAdapter:
    """Exact-identity ChinaDB renderer; dialect is chosen by compatibility mode."""

    adapter_id: str
    target_id: str
    mode_dialects: Mapping[str, str]
    adapter_version: str = "1.0.0"
    protocol_version: str = "1.0"

    @property
    def target_profile_id(self) -> str:
        return f"chinadb-{self.target_id}-local-adapter"

    @property
    def adapter_digest(self) -> str:
        return _canonical_digest(
            {
                "adapterId": self.adapter_id,
                "adapterVersion": self.adapter_version,
                "protocolVersion": self.protocol_version,
                "targetId": self.target_id,
                "targetProfileId": self.target_profile_id,
                "allowedModes": sorted(self.mode_dialects),
                "renderer": "sqlglot-expression.sql",
                "rendererVersion": _SQLGLOT_VERSION,
                "unsupportedLevel": "RAISE",
            }
        )

    def dialect_for(self, compatibility_mode: str) -> str | None:
        return self.mode_dialects.get(compatibility_mode)

    def emit(self, expression: exp.Expression, *, dialect: str) -> AdapterEmission:
        if dialect not in set(self.mode_dialects.values()):
            raise ValueError(f"ChinaDB adapter {self.adapter_id} does not own dialect {dialect}")
        input_digest = _canonical_digest(expression.dump())
        rendered = expression.sql(
            dialect=dialect,
            pretty=True,
            unsupported_level=ErrorLevel.RAISE,
        )
        output_digest = _digest_text(rendered)
        rule_id = "chinadb.local-sqlglot-target-emitter"
        rule_version = "1.0.0"
        rule_digest = _canonical_digest(
            {
                "ruleId": rule_id,
                "ruleVersion": rule_version,
                "adapterDigest": self.adapter_digest,
                "targetDialect": dialect,
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


def _adapter(target_id: str, modes: Mapping[str, str]) -> ChinaDbLocalAdapter:
    return ChinaDbLocalAdapter(
        adapter_id=f"chinadb.{target_id}.target-adapter.v1",
        target_id=target_id,
        mode_dialects=modes,
    )


CHINADB_LOCAL_ADAPTERS: tuple[ChinaDbLocalAdapter, ...] = (
    _adapter("dm8", _ORACLE),
    _adapter("kingbasees", _KINGBASE),
    _adapter("opengauss", _POSTGRES),
    _adapter("tidb", _MYSQL),
    _adapter("gbase-8s", _GBASE_8S),
    _adapter("gbase-8c", _POSTGRES),
    _adapter("gbase-8a", _MYSQL),
    _adapter("highgo-hgdb", _POSTGRES),
    _adapter("oceanbase-oracle", _ORACLE),
    _adapter("oceanbase-mysql", _MYSQL),
    _adapter("gaussdb-oracle", _ORACLE),
    _adapter("gaussdb-m", _GAUSSDB_M),
    _adapter("goldendb", _MYSQL),
)

_BY_ID = {adapter.adapter_id: adapter for adapter in CHINADB_LOCAL_ADAPTERS}


def chinadb_adapter_by_id(adapter_id: str) -> ChinaDbLocalAdapter | None:
    return _BY_ID.get(adapter_id)


def chinadb_local_adapter_count() -> int:
    return len(CHINADB_LOCAL_ADAPTERS)
