from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .models import EntitySpec, FieldSpec, RelationSpec, SynthesisRequest
from .rendering import clean

DOCUMENTATION_STATUS = "GENERATED_REVIEW_REQUIRED"
DOCUMENT_SOURCE_REFS: dict[str, tuple[str, ...]] = {
    "docs/ARCHITECTURE.md": ("approved-request", "PG054"),
    "docs/MIGRATION_GUIDE.md": ("approved-request", "PG114", "PG175"),
    "docs/CHANGE_HISTORY.md": ("approved-request", "PG175"),
    "docs/DATABASE_DESIGN.md": ("approved-request", "PG113", "PG114"),
}

_SQL_TYPES = {
    "string": "text",
    "integer": "bigint",
    "number": "numeric(20,6)",
    "boolean": "boolean",
    "datetime": "timestamptz",
}


def _markdown(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("|", "\\|")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
    )


def _block(value: str, *, indentation: int = 8) -> str:
    return value.replace("\n", "\n" + (" " * indentation))


def _value(item: Mapping[str, Any], key: str, default: str = "—") -> str:
    value = item.get(key, default)
    if isinstance(value, list):
        return ", ".join(_markdown(entry) for entry in value) or default
    return _markdown(value)


def _records_table(
    records: Iterable[Mapping[str, Any]],
    columns: tuple[tuple[str, str], ...],
    *,
    empty: str,
) -> str:
    rows = list(records)
    if not rows:
        return empty
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    body = [
        "| " + " | ".join(_value(record, key) for _, key in columns) + " |"
        for record in rows
    ]
    return "\n".join((header, divider, *body))


def _approval_metadata(request: SynthesisRequest) -> str:
    approval = request.raw["approval"]
    return "\n".join(
        (
            "| 项目 | 值 |",
            "|---|---|",
            f"| 项目名称 | `{request.project_name}` |",
            f"| 文档状态 | `{DOCUMENTATION_STATUS}` |",
            f"| 需求基线 | `sha256:{approval['approved_payload_sha256']}` |",
            f"| 审批人 | {_markdown(approval['approved_by'])} |",
            f"| 审批时间 | `{approval['approved_at']}` |",
            "| 外部评审/运行证据 | `NOT_RUN` |",
        )
    )


def _requirements(request: SynthesisRequest) -> str:
    return _records_table(
        request.raw["requirements"],
        (("ID", "id"), ("优先级", "priority"), ("需求", "statement"), ("状态", "status")),
        empty="无需求记录。",
    )


def _architecture(request: SynthesisRequest) -> str:
    target_rows = "\n".join(
        (
            f"| `{target.language}` | `{target.framework}` | `{target.runtime}` | "
            f"`{target.port}` | `{request.persistence}` | `{request.auth_mode}` |"
        )
        for target in request.targets
    )
    entities = "\n".join(
        f"| `{entity.singular}` | `{entity.plural}` | {len(entity.fields)} | CRUD API |"
        for entity in request.entities
    )
    actors = _records_table(
        request.raw.get("actors", []),
        (("ID", "id"), ("名称", "name"), ("类型", "kind")),
        empty="未声明独立参与者。",
    )
    permissions = _records_table(
        request.raw["permissions"],
        (("参与者", "actor"), ("动作", "action"), ("资源", "resource"), ("效果", "effect")),
        empty="无权限记录；运行时必须默认拒绝。",
    )
    quality = _records_table(
        request.raw.get("quality_attributes", []),
        (("ID", "id"), ("属性", "name"), ("场景", "scenario"), ("度量", "measure")),
        empty="尚未声明质量属性。",
    )
    constraints = _records_table(
        request.raw.get("constraints", []),
        (("ID", "id"), ("类别", "category"), ("约束", "statement"), ("硬约束", "hard")),
        empty="尚未声明约束。",
    )
    assumptions = _records_table(
        request.raw.get("assumptions", []),
        (("ID", "id"), ("假设", "statement"), ("状态", "status"), ("影响", "impact")),
        empty="尚未声明假设。",
    )
    target_nodes = "\n".join(
        f'    {target.language}["{target.language}: {target.framework} {target.runtime}"]'
        for target in request.targets
    )
    target_edges = "\n".join(f"    gateway --> {target.language}" for target in request.targets)
    adr_rows = "\n".join(
        (
            "| ADR-001 | 以同一 PSIR 生成多语言、同语义的 monorepo 目标 | "
            "`GENERATED_REVIEW_REQUIRED` | 各目标真实构建、测试与启动 |",
            f"| ADR-002 | 持久化配置采用 `{request.persistence}` | "
            "`GENERATED_REVIEW_REQUIRED` | 数据库迁移、恢复与一致性验证 |",
            f"| ADR-003 | 认证配置采用 `{request.auth_mode}`，策略失败时默认拒绝 | "
            "`GENERATED_REVIEW_REQUIRED` | 身份提供商和负向权限旅程 |",
        )
    )
    security_boundary = (
        f"认证模式为 `{request.auth_mode}`。身份缺失、租户上下文缺失、"
        "未知动作或策略计算失败"
        "\n均必须默认拒绝；不得从客户端自报头推导可信租户身份。"
        if request.requires_authentication
        else (
            "认证模式为 `none`，当前 starter 不提供生产身份或租户隔离保证。"
            "切换到认证配置时必须"
            "\n重新审批基线，并验证身份缺失、未知动作和策略失败的默认拒绝行为。"
        )
    )
    return clean(
        f"""
        # 架构设计文档

        {_block(_approval_metadata(request))}

        ## 1. 目标与范围

        {_markdown(request.description)}

        本文档由已审批的 Project Synthesis IR 自动生成，描述当前任务的目标架构。
        它不是架构委员会审批、生产部署或容量验证证据；这些状态均保持 `NOT_RUN`。

        ## 2. 已审批需求

        {_block(_requirements(request))}

        ## 3. 系统上下文

        ```mermaid
        flowchart LR
            actor["API user / trusted workload"]
            gateway["Authenticated API boundary"]
        {_block(target_nodes)}
            store["{request.persistence} persistence"]
            actor --> gateway
        {_block(target_edges)}
            gateway --> store
        ```

        所有目标实现共享同一需求基线、API 语义和证据边界；
        各语言的构建、测试和启动证据
        必须独立产生，不得由其他目标的结果推断。

        ## 4. 目标运行时

        | 语言 | 框架 | 运行时 | 端口 | 持久化 | 认证 |
        |---|---|---|---:|---|---|
        {_block(target_rows)}

        ## 5. 领域模块

        | 实体 | 集合/表名 | 业务字段数 | 责任 |
        |---|---|---:|---|
        {_block(entities)}

        详细字段、关系、索引和租户隔离设计见 `docs/DATABASE_DESIGN.md`。

        ## 6. 参与者与权限边界

        ### 参与者

        {_block(actors)}

        ### 权限

        {_block(permissions)}

        {_block(security_boundary)}

        ## 7. 质量属性

        {_block(quality)}

        ## 8. 约束与假设

        ### 约束

        {_block(constraints)}

        ### 假设

        {_block(assumptions)}

        ## 9. 架构决策记录

        | ADR | 决策 | 状态 | 后续证据 |
        |---|---|---|---|
        {_block(adr_rows)}

        ## 10. 交付与运维边界

        - 本地验证步骤：`docs/LOCAL_RUN.md`
        - 云部署交接：`docs/CLOUD_DEPLOYMENT.md`
        - 数据迁移与回退：`docs/MIGRATION_GUIDE.md`
        - 变更影响与历史：`docs/CHANGE_HISTORY.md`
        - 运行手册：`operations/runbook.md`

        镜像解析、生产网络、密钥供应、数据库执行、告警投递、备份恢复、容量与 SLO
        均需单独授权并取得可重放证据；当前状态为 `NOT_RUN`。
        """
    )


def _relationship_field_type(
    request: SynthesisRequest,
    entity: EntitySpec,
    field: FieldSpec,
) -> str:
    is_foreign_identifier = any(
        relation.source == entity.singular
        and relation.source_field == field.name
        and relation.target_field == "id"
        for relation in request.relations
    )
    return "uuid" if is_foreign_identifier else _SQL_TYPES[field.type]


def _er_relation(relation: RelationSpec) -> str:
    source = relation.source.upper()
    target = relation.target.upper()
    connector = {
        "one-to-one": "||--||" if relation.required else "||--o|",
        "one-to-many": "||--o{",
        "many-to-one": "}o--||" if relation.required else "}o--o|",
        "many-to-many": "}o--o{",
    }[relation.kind]
    return f'    {source} {connector} {target} : "{relation.kind}"'


def _er_diagram(request: SynthesisRequest) -> str:
    blocks = ["erDiagram"]
    for entity in request.entities:
        blocks.append(f"    {entity.singular.upper()} {{")
        if request.requires_database:
            blocks.append("        string tenant_id PK")
            blocks.append("        uuid id PK")
        else:
            blocks.append("        string id PK")
        for field in entity.fields:
            data_type = (
                _relationship_field_type(request, entity, field)
                if request.requires_database
                else field.type
            ).replace("(", "_").replace(")", "").replace(",", "_")
            blocks.append(f"        {data_type} {field.name}")
        blocks.append("    }")
    blocks.extend(_er_relation(relation) for relation in request.relations)
    return "\n".join(blocks)


def _entity_sections(request: SynthesisRequest) -> str:
    sections: list[str] = []
    for entity in request.entities:
        if request.requires_database:
            system_rows = [
                "| `tenant_id` | tenant boundary | `text` | 否 | 复合主键；非空检查 |",
                "| `id` | entity identifier | `uuid` | 否 | 复合主键 |",
            ]
            field_rows = []
            for field in entity.fields:
                relation_note = (
                    "租户内外键成员"
                    if any(
                        relation.source == entity.singular and relation.source_field == field.name
                        for relation in request.relations
                    )
                    else "—"
                )
                field_rows.append(
                    f"| `{field.name}` | `{field.type}` | "
                    f"`{_relationship_field_type(request, entity, field)}` | "
                    f"{'否' if field.required else '是'} | {relation_note} |"
                )
        else:
            system_rows = [
                "| `id` | entity identifier | `NOT_APPLICABLE` | 否 | 运行时模型标识，未生成物理列 |",
            ]
            field_rows = [
                (
                    f"| `{field.name}` | `{field.type}` | `NOT_APPLICABLE` | "
                    f"{'否' if field.required else '是'} | 内存模型字段 |"
                )
                for field in entity.fields
            ]
        rows = "\n".join((*system_rows, *field_rows))
        physical_name = f"`app.{entity.plural}`" if request.requires_database else "`NOT_APPLICABLE`"
        sections.append(
            clean(
                f"""
                ### `{entity.singular}` → {physical_name}

                | 字段 | 逻辑类型 | 物理类型 | 可空 | 约束/说明 |
                |---|---|---|---|---|
                {_block(rows, indentation=16)}
                """
            )
        )
    return "\n\n".join(sections)


def _database_design(request: SynthesisRequest) -> str:
    physical_status = "GENERATED_NOT_APPLIED" if request.requires_database else "NOT_APPLICABLE"
    relation_rows = "\n".join(
        (
            f"| `{relation.source}` | `{relation.source_field or '—'}` | `{relation.kind}` | "
            f"`{relation.target}` | `{relation.target_field or '—'}` | "
            f"{'是' if relation.required else '否'} |"
        )
        for relation in request.relations
    ) or "| — | — | — | — | — | — |"
    database_rules = [
        rule
        for rule in request.raw["business_rules"]
        if rule.get("enforcement") == "database"
        or (
            isinstance(rule.get("predicate"), dict)
            and rule["predicate"].get("type") == "field-comparison"
        )
    ]
    rules = _records_table(
        database_rules,
        (("ID", "id"), ("规则", "statement"), ("声明执行层", "enforcement")),
        empty="当前基线没有可编译为数据库 CHECK 的字段比较规则。",
    )
    if request.requires_database:
        physical = clean(
            """
            - PostgreSQL 版本配置：`17.5`
            - Schema：`app`
            - 初始迁移：`database/migrations/001_initial.sql`
            - 迁移清单：`database/migrations/manifest.json`
            - 执行入口：`database/apply-migrations.sh`
            - 策略：仅向前迁移（forward-only）
            """
        )
        isolation = clean(
            """
            每张业务表使用复合主键 `(tenant_id, id)`，并为 `tenant_id` 建索引。
            PostgreSQL RLS 同时启用 `ENABLE` 与 `FORCE`；`tenant_isolation` 策略使用
            `current_setting('app.tenant_id', true)` 进行 `USING` 与 `WITH CHECK` 判断。
            所有关系外键都包含 `tenant_id`，删除策略为 `RESTRICT`。
            """
        )
    else:
        physical = (
            "当前持久化配置为 `in-memory`，没有生成 PostgreSQL DDL、迁移脚本或物理索引；"
            "相关状态为 `NOT_APPLICABLE`。"
        )
        isolation = (
            "当前内存配置没有实现数据库级租户隔离。若未来切换到持久化数据库，"
            "必须重新审批任务基线并"
            "生成新的输出目录，不得把内存模型直接视为已实施的租户隔离。"
        )
    connection_boundary = (
        "数据库连接只能通过 `ELMOS_DATABASE_URL_FILE` 的密钥引用提供，连接值不得写入源码、"
        "\n环境转储、日志、证据或归档。"
        if request.requires_database
        else "当前任务不需要数据库连接；不得为内存配置生成或保存占位数据库凭据。"
    )
    return clean(
        f"""
        # 数据库设计文档

        {_block(_approval_metadata(request))}

        ## 1. 设计状态

        | 项目 | 状态 |
        |---|---|
        | 逻辑数据模型 | `GENERATED_REVIEW_REQUIRED` |
        | 物理数据库设计 | `{physical_status}` |
        | 数据库迁移执行 | `NOT_RUN` |
        | 数据一致性/恢复验证 | `NOT_RUN` |

        ## 2. 数据模型

        ```mermaid
        {_block(_er_diagram(request))}
        ```

        ## 3. 实体与字段

        {_block(_entity_sections(request))}

        ## 4. 关系与参照完整性

        | 源实体 | 源字段 | 关系 | 目标实体 | 目标字段 | 必需 |
        |---|---|---|---|---|---|
        {_block(relation_rows)}

        ## 5. 业务约束

        {_block(rules)}

        应用规则与数据库规则必须保持同一需求来源；
        不能通过弱化类型、删除约束或放宽可空性来通过迁移。

        ## 6. 物理实现

        {_block(physical)}

        ## 7. 索引、租户与安全

        {_block(isolation)}

        {_block(connection_boundary)}

        ## 8. 版本与演进

        - 每个迁移必须具有唯一版本、内容摘要、执行顺序与前向恢复方案。
        - 破坏性或不向后兼容变更必须经过扩展/迁移/收缩评审，并先验证混合版本窗口。
        - 备份恢复必须写入新数据库验证，不得覆盖唯一现存数据库。
        - 只有真实 PostgreSQL 执行、逐表对账、租户负向测试和恢复演练证据
          才能更新 `NOT_RUN`。
        """
    )


def _migration_guide(request: SynthesisRequest) -> str:
    database_ddl_status = "GENERATED_NOT_APPLIED" if request.requires_database else "NOT_APPLICABLE"
    if request.requires_database:
        database_steps = clean(
            """
            1. 解析并审批 PostgreSQL 17.5 目标环境与租户策略。
            2. 在隔离数据库中备份并记录摘要，不覆盖现有数据库。
            3. 通过 `ELMOS_DATABASE_URL_FILE` 提供最小权限迁移身份。
            4. 执行 `database/apply-migrations.sh`，失败即停止。
            5. 核对 `app.schema_migrations` 中的 `001_initial`、表结构、约束、索引和 RLS。
            6. 运行逐实体 CRUD、跨租户拒绝、行数/字段值对账和恢复演练。
            """
        )
        database_artifacts = (
            "`database/migrations/001_initial.sql`、`database/migrations/manifest.json`、"
            "`database/apply-migrations.sh`"
        )
    else:
        database_steps = (
            "当前任务使用 `in-memory`，物理数据库迁移为 `NOT_APPLICABLE`。未来切换 PostgreSQL "
            "必须创建并审批新基线、生成新输出目录并重新执行全部数据库验证。"
        )
        database_artifacts = "`NOT_APPLICABLE`"
    criteria = _records_table(
        request.raw["acceptance_criteria"],
        (
            ("ID", "id"),
            ("关联需求", "requirement_ids"),
            ("验收标准", "statement"),
            ("方式", "verification_type"),
        ),
        empty="无验收标准。",
    )
    return clean(
        f"""
        # 迁移与升级文档

        {_block(_approval_metadata(request))}

        ## 1. 迁移范围

        这是 `{request.project_name}` 已审批基线的首次生成与后续升级指导。
        没有提供或执行旧系统、生产数据库、真实租户数据或流量切换，
        因此“源系统迁移”“生产数据迁移”“生产切换”状态均为
        `NOT_RUN`，不得从已生成的代码或文档推断成功。

        ## 2. 状态矩阵

        | 工作流 | 当前状态 | 完成条件 |
        |---|---|---|
        | 已审批需求 → 生成工作区 | `GENERATED` | 清单内文件与摘要匹配 |
        | 目标语言构建/测试/启动 | `NOT_RUN` | 每个目标使用声明的真实工具链独立通过 |
        | 数据库 DDL 生成 | `{database_ddl_status}` | {database_artifacts} |
        | 数据迁移与对账 | `NOT_RUN` | 授权源/目标、逐字段对账、异常样本和独立复核 |
        | 灰度/切流/回退 | `NOT_RUN` | 明确流量策略、观测窗口、停止条件和证据 |
        | 外部认证 | `NOT_CERTIFIED` | 独立外部门禁 |

        ## 3. 变更前检查

        1. 核对 `requirements/approved-request.json` 的摘要与本文件需求基线一致。
        2. 阅读 `docs/ARCHITECTURE.md`、`docs/DATABASE_DESIGN.md` 和 `docs/CHANGE_HISTORY.md`。
        3. 确认目标运行时、依赖、镜像摘要、秘密引用、网络与回滚责任人。
        4. 运行 `elmos-project-synthesis verify --workspace .`，缺失工具链保持 `NOT_RUN`。
        5. 对比上一版生成清单；任何不受管理或人工修改文件都必须停止自动覆盖。

        ## 4. 数据库迁移

        {_block(database_steps)}

        ## 5. 应用升级顺序

        1. 先在隔离环境生成与验证不可变候选产物。
        2. 运行全部目标语言的构建、测试、启动和 API 契约验证。
        3. 数据库变更先证明旧/新应用混合版本兼容，再进行应用灰度。
        4. 逐步放量并监控错误率、延迟、授权拒绝、数据库耗时和数据对账差异。
        5. 超过预设阈值立即停止；不得以忽略失败、放宽权限或删除约束继续发布。

        ## 6. 验收标准

        {_block(criteria)}

        ## 7. 回退与前向恢复

        - 应用仅在数据库兼容窗口内允许回退到已知镜像摘要。
        - 数据库采用仅向前迁移；失败时使用审批过的修复迁移，
          或从备份恢复到新数据库。
        - 禁止对唯一生产数据库执行未经演练的破坏性 down migration。
        - 恢复后重新运行结构、数据、租户隔离和应用旅程验证，再决定是否切流。

        ## 8. 迁移证据清单

        - 精确源/目标版本与环境标识
        - 授权人、执行人和独立复核人
        - 迁移文件摘要、命令、开始/结束时间与退出码
        - 迁移前后逐表行数、逐字段对账与异常清单
        - 租户隔离负向结果、备份恢复结果和回退/停止决策

        上述证据尚未产生，当前保持 `NOT_RUN`。
        """
    )


def _change_history(request: SynthesisRequest) -> str:
    approval = request.raw["approval"]
    target_list = ", ".join(f"{target.language}/{target.framework}" for target in request.targets)
    version_row = (
        f"| `0.1.0` | `{approval['approved_at']}` | {_markdown(approval['approved_by'])} | "
        f"初始任务基线 | `sha256:{approval['approved_payload_sha256']}` | "
        "`GENERATED_REVIEW_REQUIRED` |"
    )
    requirements_impact = (
        f"{len(request.raw['requirements'])} 条需求、"
        f"{len(request.raw['acceptance_criteria'])} 条验收标准进入基线"
    )
    security_impact = (
        f"| 安全 | 认证 `{request.auth_mode}`，权限默认拒绝，"
        "租户边界不得由客户端自报 | `NOT_RUN` |"
    )
    database_impact = (
        "生成 PostgreSQL 初始 schema、复合租户主键、索引、RLS、外键和迁移清单；尚未执行。"
        if request.requires_database
        else "使用内存持久化；未生成物理数据库迁移，数据库影响为 NOT_APPLICABLE。"
    )
    return clean(
        f"""
        # 修改历史与变更影响

        {_block(_approval_metadata(request))}

        ## 1. 版本记录

        | 版本 | 时间 | 责任人 | 类型 | 基线摘要 | 状态 |
        |---|---|---|---|---|---|
        {_block(version_row)}

        ## 2. 本次任务变更摘要

        - 建立 `{request.project_name}` 的已审批需求、PSIR、Project Blueprint、资产图与构建图。
        - 生成 {len(request.entities)} 个领域实体、{len(request.relations)} 条关系及其 API/数据契约。
        - 生成目标：{_markdown(target_list)}。
        - 新增架构、迁移、修改历史和数据库设计 Markdown 文档。
        - 生成清单请求封装摘要：`sha256:{request.request_hash}`。

        ## 3. 影响分析

        | 影响域 | 结论 | 验证状态 |
        |---|---|---|
        | 需求/行为 | {requirements_impact} | `GENERATED` |
        | API | 各目标生成同一实体 CRUD 与健康检查契约 | `NOT_RUN` |
        | 数据库 | {database_impact} | `{'NOT_RUN' if request.requires_database else 'NOT_APPLICABLE'}` |
        {_block(security_impact)}
        | 运维 | 生成运行手册、SLO/可观测性契约和部署交接 | `NOT_RUN` |
        | 外部系统 | 未执行真实提供商、生产流量、真实数据或第三方认证 | `NOT_RUN` |

        ## 4. 需求追踪

        {_block(_requirements(request))}

        ## 5. 后续修改规则

        1. 任何需求、实体、字段、关系、权限、目标运行时或部署策略变化，
           都要创建新的审批基线和输出目录。
        2. 在本表追加新版本记录，不覆盖或重写历史；
           同时绑定提交摘要、生成清单和审批主体。
        3. 数据变更同步更新 `docs/DATABASE_DESIGN.md` 与 `docs/MIGRATION_GUIDE.md`，
           并提供前向恢复方案。
        4. 架构决策同步追加 ADR；安全、租户或合同影响必须由对应责任人复核。
        5. 只有真实执行证据才能把 `NOT_RUN` 更新为通过或失败；生成器不得自行宣布认证。
        """
    )


def render_project_documentation(request: SynthesisRequest) -> dict[str, str]:
    return {
        "docs/ARCHITECTURE.md": _architecture(request),
        "docs/MIGRATION_GUIDE.md": _migration_guide(request),
        "docs/CHANGE_HISTORY.md": _change_history(request),
        "docs/DATABASE_DESIGN.md": _database_design(request),
    }
