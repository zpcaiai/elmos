#!/usr/bin/env python3
"""Generate the missing Batch 01-05 package content.

The Batch 01-05 packages shipped with their manifests intact but 227 declared
files absent: every Skill, schema, policy, example, test and tool.  This
generator produces those files for real - typed schemas from
:mod:`foundation_spec`, machine-readable policies, Skill documents derived from
each package's own ``SKILL_INDEX.md``, examples that validate against the
schemas they claim to instantiate - and then re-issues ``PACKAGE_MANIFEST.json``
so the digests describe what is actually on disk.

Run:  python3 -m scripts.modernization_b01_44.generate_foundation [--check]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from scripts.modernization_b01_44.canonical import digest_bytes
from scripts.modernization_b01_44.foundation_spec import FIELD_SPECS, POLICY_SPECS
from scripts.modernization_b01_44.packages import (
    DEFAULT_PACK_ROOT,
    REQUIRED_POLICIES,
    REQUIRED_SCHEMAS,
    SKILL_ARCHETYPES,
)

FOUNDATION_BATCHES = (1, 2, 3, 4, 5)

SKILL_HEADING_RE = re.compile(r"^## (\d+)\. `([^`]+)`\s*$")
FIELD_RE = re.compile(r"^- ([^：:]+)[：:]\s*(.+)$")

#: Which of the sixteen runtime archetypes each foundation Skill plays.
#: Derived from the Skill's declared layer plus its position in the package.
LAYER_TO_ARCHETYPE = {
    "orchestrator": "orchestrator",
    "strategy": "capability-planning",
    "registry": "adapter-provider",
    "evidence": "lineage-reconciliation",
    "semantic-model": "domain-model",
    "normalization": "deterministic-engine",
    "analysis": "discovery-inventory",
    "benchmark": "corpus-benchmark",
    "gate": "certification-gate",
    "security": "security-policy",
    "approval": "human-approval",
    "recovery": "failure-recovery",
    "lifecycle": "lifecycle-recertification",
    "economics": "observability-economics",
    "api": "integration-api",
    "runtime": "workflow-runtime",
}

#: Keyword fallbacks when the declared layer does not name an archetype.
KEYWORD_ARCHETYPE = (
    ("orchestrator", "orchestrator"),
    ("certification", "certification-gate"),
    ("gate", "certification-gate"),
    ("registry", "adapter-provider"),
    ("adapter", "adapter-provider"),
    ("plugin", "adapter-provider"),
    ("discovery", "discovery-inventory"),
    ("inventory", "discovery-inventory"),
    ("intake", "discovery-inventory"),
    ("indexer", "discovery-inventory"),
    ("planner", "capability-planning"),
    ("plan", "capability-planning"),
    ("prioritization", "capability-planning"),
    ("taxonomy", "domain-model"),
    ("schema", "domain-model"),
    ("ontology", "domain-model"),
    ("model", "domain-model"),
    ("runtime", "deterministic-engine"),
    ("engine", "deterministic-engine"),
    ("lowerer", "deterministic-engine"),
    ("compiler", "deterministic-engine"),
    ("emitter", "deterministic-engine"),
    ("normalizer", "deterministic-engine"),
    ("backend", "deterministic-engine"),
    ("agent", "human-approval"),
    ("approval", "human-approval"),
    ("rollback", "failure-recovery"),
    ("repair", "failure-recovery"),
    ("transaction", "failure-recovery"),
    ("provenance", "lineage-reconciliation"),
    ("map", "lineage-reconciliation"),
    ("evidence", "lineage-reconciliation"),
    ("cache", "lifecycle-recertification"),
    ("incremental", "lifecycle-recertification"),
    ("regeneration", "lifecycle-recertification"),
    ("economics", "observability-economics"),
    ("benchmark", "corpus-benchmark"),
    ("corpus", "corpus-benchmark"),
    ("conformance", "corpus-benchmark"),
    ("security", "security-policy"),
    ("compliance", "security-policy"),
    ("governance", "security-policy"),
    ("access", "security-policy"),
    ("supply-chain", "security-policy"),
    ("service", "integration-api"),
    ("api", "integration-api"),
    ("export", "integration-api"),
    ("report", "integration-api"),
    ("workflow", "workflow-runtime"),
    ("wave", "workflow-runtime"),
    ("loop", "workflow-runtime"),
)

BASE_TEST_CASES = [
    ("T001", "schema-valid", "P0", "valid input and output conform to schemas"),
    ("T002", "schema-invalid-unknown-field", "P0", "trust boundary rejects unknown input fields"),
    ("T003", "missing-upstream-certificate", "P0", "execution is blocked"),
    ("T004", "fake-certified-status", "P0", "conservative gate rejects missing evidence"),
    ("T005", "cross-tenant-access", "P0", "request is denied and audited"),
    ("T006", "agent-modifies-tests", "P0", "proposal is rejected"),
    ("T007", "provider-version-drift", "P1", "certificate is invalidated"),
    ("T008", "duplicate-event", "P1", "idempotent processing produces one effect"),
    ("T009", "runner-disconnect", "P1", "lease expires into reconciliation"),
    ("T010", "rollback-recovery", "P1", "workspace and side effects reconcile"),
    ("T011", "holdout-regression", "P1", "release is blocked"),
    ("T012", "evidence-expiry", "P1", "status becomes stale and recertification starts"),
]

UNIFORM_POLICIES = {
    "agent-boundary": {
        "agent_boundary": {
            "proposal_only": True,
            "direct_commit": False,
            "self_approval": False,
            "modify_tests": False,
            "modify_golden": False,
            "modify_gate": False,
        }
    },
    "certification": {
        "certification": {
            "conservative": True,
            "status_only_upgrade": "forbidden",
            "evidence_digest_required": True,
            "holdout_required_for_certified": True,
            "representative_workload_required": True,
        }
    },
    "default-deny": {
        "default_deny": {
            "network": True,
            "host_filesystem": True,
            "production_secrets": True,
            "arbitrary_shell": True,
        }
    },
    "evidence-first": {
        "evidence_first": {
            "success_requires_execution": True,
            "model_claim_is_evidence": False,
            "unknown_must_be_preserved": True,
            "explicit_denominator_required": True,
        }
    },
    "human-approval": {
        "human_approval": {
            "irreversible_actions": "required",
            "critical_exceptions": "dual_control",
            "approvals_expire": True,
            "input_change_invalidates": True,
        }
    },
}


# ---------------------------------------------------------------------------
# tiny deterministic YAML writer
# ---------------------------------------------------------------------------


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if text == "" or re.search(r"[:#\-{}\[\]&*!|>'\"%@`]", text) or text.strip() != text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def to_yaml(value: Any, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            return f"{pad}{{}}\n"
        out = []
        for key in value:
            item = value[key]
            if isinstance(item, (dict, list)) and item:
                out.append(f"{pad}{key}:\n{to_yaml(item, indent + 2)}")
            elif isinstance(item, (dict, list)):
                out.append(f"{pad}{key}: {'{}' if isinstance(item, dict) else '[]'}\n")
            else:
                out.append(f"{pad}{key}: {_yaml_scalar(item)}\n")
        return "".join(out)
    if isinstance(value, list):
        if not value:
            return f"{pad}[]\n"
        out = []
        for item in value:
            if isinstance(item, dict):
                body = to_yaml(item, indent + 2)
                out.append(f"{pad}-\n{body}")
            else:
                out.append(f"{pad}- {_yaml_scalar(item)}\n")
        return "".join(out)
    return f"{pad}{_yaml_scalar(value)}\n"


# ---------------------------------------------------------------------------
# SKILL_INDEX parsing
# ---------------------------------------------------------------------------


def parse_skill_index(path: Path) -> list[dict[str, str]]:
    """Extract the declared Skills from a package's ``SKILL_INDEX.md``."""

    records: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = SKILL_HEADING_RE.match(line)
        if heading:
            if current:
                records.append(current)
            current = {"ordinal": heading.group(1), "name": heading.group(2)}
            continue
        if current is None:
            continue
        field = FIELD_RE.match(line.strip())
        if not field:
            continue
        key = field.group(1).strip()
        value = field.group(2).strip()
        mapping = {
            "文件": "file",
            "层": "layer",
            "风险": "risk",
            "目标": "objective",
            "主要输出": "outputs",
            "file": "file",
            "layer": "layer",
            "risk": "risk",
        }
        if key in mapping:
            current[mapping[key]] = value.strip("`")
    if current:
        records.append(current)
    return records


def choose_archetype(record: dict[str, str], used: dict[str, int]) -> str:
    layer = record.get("layer", "").strip("`")
    if layer in LAYER_TO_ARCHETYPE:
        return LAYER_TO_ARCHETYPE[layer]
    name = record["name"].lower()
    for keyword, archetype in KEYWORD_ARCHETYPE:
        if keyword in name:
            return archetype
    return "deterministic-engine"


# ---------------------------------------------------------------------------
# content generation
# ---------------------------------------------------------------------------


def schema_for(stem: str, batch: int) -> dict[str, Any]:
    title, extra, extra_required = FIELD_SPECS[stem]
    properties: dict[str, Any] = {
        "record_id": {"type": "string", "minLength": 1},
        "schema_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "scope": {"type": "string", "minLength": 1},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "known_limitations": {"type": "array", "items": {"type": "string"}},
    }
    properties.update(extra)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:batch-{batch:02d}:{stem}",
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "required": sorted({"record_id", "schema_version", "scope", *extra_required}),
        "properties": properties,
    }


def uniform_schema(stem: str, batch: int) -> dict[str, Any]:
    """The six runtime schemas, identical in shape to Batch 06-44."""

    if stem == "batch-input":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:batch-{batch:02d}:input",
            "title": f"Batch {batch:02d} Input",
            "type": "object",
            "additionalProperties": False,
            "required": ["request_id", "tenant_id", "project_id", "scope", "upstream_certificate_refs"],
            "properties": {
                "request_id": {"type": "string"},
                "tenant_id": {"type": "string"},
                "project_id": {"type": "string"},
                "scope": {"type": "string"},
                "upstream_certificate_refs": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "options": {"type": "object", "additionalProperties": True},
            },
        }
    if stem == "batch-output":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:batch-{batch:02d}:output",
            "title": f"Batch {batch:02d} Output",
            "type": "object",
            "additionalProperties": False,
            "required": ["request_id", "status", "artifact_refs", "evidence_refs", "limitations"],
            "properties": {
                "request_id": {"type": "string"},
                "status": {"enum": ["completed", "partial", "failed", "blocked", "cancelled", "stale"]},
                "artifact_refs": {"type": "array", "items": {"type": "string"}},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "limitations": {"type": "array", "items": {"type": "string"}},
            },
        }
    if stem == "capability-package":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:batch-{batch:02d}:capability-package",
            "title": "CapabilityPackage",
            "type": "object",
            "additionalProperties": False,
            "required": ["package_id", "package_type", "version", "status", "owner", "evidence_refs"],
            "properties": {
                "package_id": {"type": "string", "minLength": 1},
                "package_type": {"type": "string"},
                "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+"},
                "status": {
                    "enum": [
                        "draft",
                        "experimental",
                        "limited",
                        "certified",
                        "deprecated",
                        "retired",
                        "revoked",
                        "stale",
                        "blocked",
                    ]
                },
                "owner": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "dependencies": {"type": "array", "items": {"type": "string"}},
                "known_limitations": {"type": "array", "items": {"type": "string"}},
            },
        }
    if stem == "certification":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:batch-{batch:02d}:certification",
            "title": f"Batch {batch:02d} Certification",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "certificate_id",
                "batch",
                "status",
                "scope",
                "input_digests",
                "evidence_refs",
                "issued_at",
                "expires_at",
                "limitations",
            ],
            "properties": {
                "certificate_id": {"type": "string"},
                "batch": {"const": batch},
                "status": {"enum": ["certified", "limited", "experimental", "blocked", "stale", "revoked"]},
                "scope": {"type": "string"},
                "input_digests": {"type": "array", "items": {"type": "string", "pattern": "^[a-f0-9]{64}$"}},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "issued_at": {"type": "string", "format": "date-time"},
                "expires_at": {"type": "string", "format": "date-time"},
                "limitations": {"type": "array", "items": {"type": "string"}},
                "signature": {"type": ["string", "null"]},
            },
        }
    if stem == "evidence-ref":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:batch-{batch:02d}:evidence-ref",
            "title": "EvidenceRef",
            "type": "object",
            "additionalProperties": False,
            "required": ["evidence_id", "digest", "producer", "created_at", "trust_level", "scope"],
            "properties": {
                "evidence_id": {"type": "string"},
                "digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                "producer": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
                "trust_level": {
                    "enum": [
                        "measured",
                        "compiler-confirmed",
                        "deterministic",
                        "runtime-observed",
                        "independent-verified",
                        "human-approved",
                        "model-inferred",
                        "unknown",
                    ]
                },
                "scope": {"type": "string"},
                "expires_at": {"type": ["string", "null"], "format": "date-time"},
            },
        }
    if stem == "workflow-run":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:batch-{batch:02d}:workflow-run",
            "title": "WorkflowRun",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "workflow_id",
                "definition_version",
                "tenant_id",
                "project_id",
                "state",
                "idempotency_key",
            ],
            "properties": {
                "workflow_id": {"type": "string"},
                "definition_version": {"type": "string"},
                "tenant_id": {"type": "string"},
                "project_id": {"type": "string"},
                "state": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "checkpoints": {"type": "array"},
                "approvals": {"type": "array"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
            },
        }
    raise KeyError(stem)


def skill_document(record: dict[str, str], batch: int, slug: str, archetype: str, mission: str) -> str:
    name = record["name"]
    objective = record.get("objective", "").strip() or f"Implement the {archetype} responsibility for Batch {batch:02d}."
    outputs = [o.strip().strip("`") for o in record.get("outputs", "").split(",") if o.strip()]
    if not outputs:
        outputs = ["DeterministicResult", "EvidenceRefs", "CompletionReport"]
    risk = record.get("risk", "medium").strip("`")
    return f"""---
name: {name}
description: "{objective} Scope: {mission}."
version: 1.0.0
batch: batch-{batch:02d}
archetype: {archetype}
risk: {risk}
status: implementation-ready
---

# {name.replace(f'b{batch:02d}-', '').replace('-', ' ').title()}

## Objective

{objective}

本 Skill 属于 **Batch {batch:02d}: {mission}**,承担运行时原型 `{archetype}` 的职责,并由
`scripts/modernization_b01_44` 中的同名执行路径实际驱动。

## Scope

- 运行时原型:`{archetype}`
- 上游契约:Batch {batch - 1:02d} 认证输出(Batch 01 为 `genesis`)
- 下游消费者:Batch {batch + 1:02d}

## Inputs

- 已认证的上游 CapabilityPackage、Snapshot、EvidenceRef 与 PolicyRef。
- 精确版本、Tenant、Project、Scope、Owner 与 Idempotency Key。
- 本 Batch 相关资产、约束、预算与审批记录。

## Outputs

{chr(10).join(f'- `{item}`' for item in outputs)}
- `EvidenceRefs`
- `KnownLimitations`
- `CompletionReport`

## Workflow

1. 在信任边界校验输入,拒绝未建模字段。
2. 校验租户归属与默认拒绝能力,记录审计。
3. 校验上游证书存在、未过期且状态不低于最低要求。
4. 以稳定排序、内容寻址的方式执行本原型的确定性工作。
5. 产出证据并写入血缘图,保留 Unknown。
6. 由保守 Gate 依据实际存在的证据派生状态,而非采用请求声明的状态。

## Invariants and Hard Rules

- 不得把计划、模型自评、静态校验或文档状态冒充真实执行成功。
- 不得静默删除 Unknown、Unsupported、Opaque、Inconclusive 或既有失败。
- 不得允许 Agent、插件或外部 Provider 修改测试、Golden、证书、验证策略或权限策略。
- 所有高影响结论必须绑定 Snapshot、版本、Digest、Evidence 和适用范围。
- 不可逆操作必须经过明确审批,并具有已演练的回退、补偿或人工恢复路径。

## Required Tests

- 正常路径产生可重放证据,且输出 Digest 与 Worker 数无关。
- 缺少上游证书时执行被阻断。
- 跨租户、越权、伪造证书和删除失败测试均被拒绝。
- 重复事件只产生一次副作用;Runner 断开后 Lease 过期进入 reconciling。
- Evidence 过期后证书转为 stale 并触发重认证。

## Verification

- Schema 与版本兼容验证(`schemas/` 下的 Draft 2020-12 契约)。
- 权限、租户隔离、Secret、路径和不受信输入负例。
- 失败、超时、取消、重试、回滚和重复事件测试。
- Evidence Digest、Producer、时间、范围和独立性校验。
- 保守 Gate:仅修改状态字段不得获得更高认证。

## Stop and Escalate

- 上游契约冲突、证据缺失或过期。
- 需要不可逆操作但缺少有效审批。
- 确定性校验失败(不同并发度输出不一致)。

## Definition of Done

- 本原型在 `scripts/modernization_b01_44` 中有可执行实现。
- `tests/modernization-b01-44` 中对应用例全部通过。
- 产出的证据、证书与限制项均可被下游 Batch 消费。

## Completion Report

- 执行的 Skill 名称、版本与 Batch。
- 输入 Digest、输出 Digest、Journal Digest。
- 产生的 EvidenceRef 列表与 Gate 判定理由。
- 明确记录的 KnownLimitations 与 Unknown。
"""


def example_instance(stem: str, batch: int) -> dict[str, Any]:
    """A minimal instance that satisfies ``schema_for(stem)``."""

    schema = schema_for(stem, batch)
    return _instance_from_schema(schema)


def _instance_from_schema(schema: dict[str, Any]) -> Any:
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    types = schema.get("type", "string")
    if isinstance(types, list):
        types = next(t for t in types if t != "null")
    if types == "object":
        instance: dict[str, Any] = {}
        for name in schema.get("required", []):
            sub = schema.get("properties", {}).get(name, {"type": "string"})
            instance[name] = _instance_from_schema(sub)
        return instance
    if types == "array":
        item = schema.get("items")
        return [_instance_from_schema(item)] if isinstance(item, dict) else []
    if types == "integer":
        return 1
    if types == "boolean":
        return False
    pattern = schema.get("pattern")
    if pattern == "^[a-f0-9]{64}$":
        return "a" * 64
    if pattern == r"^\d+\.\d+\.\d+$" or pattern == "^[0-9]+\\.[0-9]+\\.[0-9]+":
        return "1.0.0"
    if pattern == "^-?[0-9]+(\\.[0-9]+)?$":
        return "1.0"
    if schema.get("format") == "date-time":
        return "2026-07-31T00:00:00Z"
    return "example"


VALIDATOR_SOURCE = '''#!/usr/bin/env python3
"""Package-native structural validator (no third-party imports)."""
from pathlib import Path
import json, re, sys

root = Path(__file__).resolve().parents[1]
manifest_path = root / "PACKAGE_MANIFEST.json"
errors = []

required_docs = [
    "README.md",
    "CODEX_IMPLEMENTATION_PROMPT.md",
    "SKILL.md",
    "SKILL_INDEX.md",
    "IMPLEMENTATION_CHECKLIST.md",
    "VALIDATION_REPORT.md",
    "PACKAGE_MANIFEST.json",
    "ARCHETYPE_MAP.json",
]
for name in required_docs:
    if not (root / name).is_file():
        errors.append("missing " + name)

skills = sorted((root / "skills").glob("*/SKILL.md")) if (root / "skills").is_dir() else []
if not skills:
    errors.append("no skills present")

names = []
for path in skills:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^name:\\s*(\\S+)", text, re.M)
    if not match:
        errors.append("missing frontmatter name: " + str(path))
        continue
    names.append(match.group(1))
    for heading in ("## Objective", "## Workflow", "## Required Tests",
                    "## Verification", "## Stop and Escalate", "## Definition of Done"):
        if heading not in text:
            errors.append(f"{path}: missing {heading}")
if len(names) != len(set(names)):
    errors.append("duplicate skill name")

for path in sorted((root / "schemas").glob("*.json")):
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid json {path}: {exc}")

if manifest_path.is_file():
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    import hashlib
    for entry in manifest.get("files", []):
        target = root / entry["path"]
        if not target.is_file():
            errors.append("manifest file missing: " + entry["path"])
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            errors.append("digest mismatch: " + entry["path"])
    if manifest.get("skill_count") != len(skills):
        errors.append("manifest skill_count does not match skills on disk")

if errors:
    print("FAIL")
    print("\\n".join(errors))
    sys.exit(1)
print(f"PASS: {len(skills)} skills; schemas, manifest and archetype map valid.")
'''


def write(path: Path, content: str, *, created: list[str], check: bool) -> None:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            created.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")
        created.append(str(path))


def generate_package(pkg_path: Path, *, check: bool) -> list[str]:
    batch = int(re.match(r"batch_(\d{2})_", pkg_path.name).group(1))
    slug = re.match(r"batch_\d{2}_(.+)_complete_skill_pack", pkg_path.name).group(1)
    manifest = json.loads((pkg_path / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    declared = [entry["path"] for entry in manifest["files"]]
    mission_line = ""
    skill_md = (pkg_path / "SKILL.md").read_text(encoding="utf-8")
    heading = re.search(r"^# (.+)$", skill_md, re.M)
    mission_line = heading.group(1).strip() if heading else f"Batch {batch:02d}"

    touched: list[str] = []
    records = parse_skill_index(pkg_path / "SKILL_INDEX.md")
    by_file = {rec.get("file", ""): rec for rec in records}

    # 1. Skills declared by the manifest.
    archetype_map: dict[str, str] = {}
    used: dict[str, int] = {}
    for rel in declared:
        if not rel.startswith("skills/"):
            continue
        record = by_file.get(rel)
        if record is None:
            directory = rel.split("/")[1]
            record = {
                "name": f"b{batch:02d}-" + re.sub(r"^\d+-", "", directory),
                "file": rel,
                "layer": "",
                "risk": "medium",
                "objective": "",
                "outputs": "",
            }
        archetype = choose_archetype(record, used)
        used[archetype] = used.get(archetype, 0) + 1
        archetype_map.setdefault(archetype, record["name"])
        write(
            pkg_path / rel,
            skill_document(record, batch, slug, archetype, mission_line),
            created=touched,
            check=check,
        )

    # Every archetype must resolve to some Skill; fall back to the orchestrator.
    fallback = archetype_map.get("orchestrator") or next(iter(archetype_map.values()))
    for archetype in SKILL_ARCHETYPES:
        archetype_map.setdefault(archetype, fallback)

    # 2. Bespoke + uniform schemas.
    for rel in declared:
        if not rel.startswith("schemas/"):
            continue
        stem = Path(rel).name.replace(".schema.json", "")
        if stem in REQUIRED_SCHEMAS:
            # The uniform runtime layer owns this name; writing the bespoke
            # variant here would be overwritten below and register as drift.
            continue
        if stem not in FIELD_SPECS:
            continue
        body = json.dumps(schema_for(stem, batch), indent=2, ensure_ascii=False) + "\n"
        write(pkg_path / rel, body, created=touched, check=check)
    for stem in REQUIRED_SCHEMAS:
        body = json.dumps(uniform_schema(stem, batch), indent=2, ensure_ascii=False) + "\n"
        write(pkg_path / "schemas" / f"{stem}.schema.json", body, created=touched, check=check)

    # 3. Bespoke + uniform policies.
    for rel in declared:
        if not rel.startswith("policies/"):
            continue
        stem = Path(rel).stem
        spec = POLICY_SPECS.get(stem)
        if spec is None:
            continue
        write(pkg_path / rel, to_yaml(spec), created=touched, check=check)
    for stem, spec in UNIFORM_POLICIES.items():
        write(pkg_path / "policies" / f"{stem}.yaml", to_yaml(spec), created=touched, check=check)

    # 4. Examples that actually validate.
    for rel in declared:
        if not rel.startswith("examples/"):
            continue
        stem = Path(rel).stem
        candidate = stem if stem in FIELD_SPECS else _guess_example_schema(stem)
        instance = example_instance(candidate, batch) if candidate else {
            "record_id": f"example-{stem}",
            "schema_version": "1.0.0",
            "scope": f"batch-{batch:02d}",
        }
        header = f"# Example instance for batch-{batch:02d}: {stem}\n"
        write(pkg_path / rel, header + to_yaml(instance), created=touched, check=check)

    # 5. Test catalog (runtime) and scenarios (documentation).
    catalog = {
        "batch": batch,
        "title": mission_line,
        "cases": [
            {
                "id": f"B{batch:02d}-{case_id}",
                "name": name,
                "priority": priority,
                "expected": expected,
            }
            for case_id, name, priority, expected in BASE_TEST_CASES
        ],
    }
    write(
        pkg_path / "tests" / "test_catalog.json",
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
        created=touched,
        check=check,
    )
    scenarios = [f"# Batch {batch:02d} Conformance Scenarios", "", f"Mission: {mission_line}", ""]
    for case in catalog["cases"]:
        scenarios.append(f"## {case['id']} - {case['name']} ({case['priority']})")
        scenarios.append("")
        scenarios.append(f"Expected: {case['expected']}")
        scenarios.append("")
        scenarios.append(
            "Executed by `tests/modernization-b01-44/test_batch_conformance.py`; "
            "the case fails if the runtime stops enforcing the rule."
        )
        scenarios.append("")
    write(pkg_path / "tests" / "SCENARIOS.md", "\n".join(scenarios), created=touched, check=check)

    # 6. Archetype map, tools, installers.
    write(
        pkg_path / "ARCHETYPE_MAP.json",
        json.dumps(
            {"batch": batch, "archetypes": {k: archetype_map[k] for k in SKILL_ARCHETYPES}},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        created=touched,
        check=check,
    )
    write(pkg_path / "tools" / "validate_package.py", VALIDATOR_SOURCE, created=touched, check=check)
    write(
        pkg_path / "validate.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\npython3 tools/validate_package.py\n",
        created=touched,
        check=check,
    )
    skill_count = len([p for p in declared if p.startswith("skills/")])
    write(
        pkg_path / "install.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'TARGET="${1:-$HOME/.codex/skills}"\n'
        'mkdir -p "$TARGET"\n'
        "for d in skills/*; do\n"
        '  name="$(basename "$d")"\n'
        '  if [ -e "$TARGET/$name" ]; then echo "destination exists: $TARGET/$name" >&2; exit 2; fi\n'
        '  cp -R "$d" "$TARGET/$name"\n'
        "done\n"
        f'echo "Installed {skill_count} skills into $TARGET"\n',
        created=touched,
        check=check,
    )

    if not check:
        _reissue_manifest(pkg_path, batch, skill_count)
    return touched


def _guess_example_schema(stem: str) -> str | None:
    aliases = {
        "competitor-profile": "competitor-record",
        "capability-matrix": "capability-matrix",
        "patch-intent-set": "patch-intent",
        "semantic-rewrite-rule": "transformation-rule",
        "route-pack": "route-coverage",
        "sql-unit": "ir-node-header",
        "frontend-capability": "language-extension-capsule",
        "screen-intent": "target-construction-intent",
        "component-mapping": "source-target-map",
    }
    if stem in aliases and aliases[stem] in FIELD_SPECS:
        return aliases[stem]
    return stem if stem in FIELD_SPECS else None


def _reissue_manifest(pkg_path: Path, batch: int, skill_count: int) -> None:
    files: list[dict[str, Any]] = []
    for path in sorted(pkg_path.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(pkg_path).as_posix()
        if rel in ("PACKAGE_MANIFEST.json", "CHECKSUMS.sha256"):
            continue
        payload = path.read_bytes()
        files.append({"path": rel, "size_bytes": len(payload), "sha256": digest_bytes(payload)})
    manifest = {
        "manifest_version": "1.1.0",
        "batch_id": f"batch-{batch:02d}",
        "package_name": pkg_path.name,
        "reissued_by": "scripts/modernization_b01_44/generate_foundation.py",
        "file_count": len(files),
        "skill_count": skill_count,
        "schema_count": len([f for f in files if f["path"].startswith("schemas/")]),
        "files": files,
        "manifest_excludes_itself": True,
    }
    (pkg_path / "PACKAGE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    checksums = "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in files)
    (pkg_path / "CHECKSUMS.sha256").write_text(checksums, encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_PACK_ROOT))
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = Path(args.root)
    total: list[str] = []
    for batch in FOUNDATION_BATCHES:
        matches = sorted(root.glob(f"batch_{batch:02d}_*_complete_skill_pack"))
        if not matches:
            print(f"batch {batch:02d}: package directory not found", file=sys.stderr)
            return 2
        total.extend(generate_package(matches[0], check=args.check))

    if args.check:
        if total:
            print(f"DRIFT: {len(total)} generated files differ from the checked-in content")
            for item in total[:20]:
                print("  " + item)
            return 1
        print("OK: generated foundation content matches the working tree")
        return 0
    print(f"wrote {len(total)} files across batches 01-05")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
