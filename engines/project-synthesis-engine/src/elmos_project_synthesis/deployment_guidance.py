from __future__ import annotations

import json
from typing import Any

from .models import TARGET_PROFILES, SynthesisRequest
from .rendering import clean

_HARDWARE: dict[str, dict[str, tuple[int, int, int]]] = {
    "java": {"minimum": (2, 4, 5), "recommended": (4, 8, 10)},
    "python": {"minimum": (2, 4, 4), "recommended": (4, 8, 8)},
    "csharp": {"minimum": (2, 4, 6), "recommended": (4, 8, 12)},
    "typescript": {"minimum": (2, 4, 4), "recommended": (4, 8, 8)},
    "go": {"minimum": (2, 2, 3), "recommended": (4, 4, 6)},
    "kotlin": {"minimum": (4, 8, 8), "recommended": (8, 16, 15)},
    "php": {"minimum": (2, 2, 2), "recommended": (4, 4, 5)},
    "rust": {"minimum": (4, 8, 10), "recommended": (8, 16, 20)},
}

_CLOUD_OPTIONS = [
    {
        "id": "google-cloud-run",
        "name": "Google Cloud Run",
        "status": "RECOMMENDED",
        "fit": "无状态 HTTP API、按请求弹性伸缩、希望减少集群运维。",
        "tradeoff": "需要外置持久化、Secret Manager 和明确的冷启动/连接池配置。",
    },
    {
        "id": "azure-container-apps",
        "name": "Azure Container Apps",
        "status": "OPTIONAL",
        "fit": "现有 Azure 租户、Managed Identity、Key Vault 与 Azure Database 团队。",
        "tradeoff": "需要独立验证环境、身份、网络、日志和修订流量切换。",
    },
    {
        "id": "aws-ecs-fargate",
        "name": "AWS ECS on Fargate",
        "status": "OPTIONAL",
        "fit": "现有 AWS 账号、ECR、IAM、VPC、ALB 和 RDS 运维体系。",
        "tradeoff": "任务角色、执行角色、网络、负载均衡和扩缩容配置项更多。",
    },
    {
        "id": "kubernetes",
        "name": "GKE / EKS / AKS Kubernetes",
        "status": "CONDITIONAL",
        "fit": "已有平台团队、集群策略、镜像准入、观测和升级能力。",
        "tradeoff": "控制面和工作负载运维成本最高，不建议只为单个 Starter 新建集群。",
    },
]


def _hardware_text(values: tuple[int, int, int]) -> str:
    cpu, memory, disk = values
    return f"{cpu} vCPU / {memory} GB RAM / {disk} GB 可用磁盘"


def _target_profile(language: str) -> dict[str, Any]:
    target = TARGET_PROFILES[language]
    minimum = _HARDWARE[language]["minimum"]
    recommended = _HARDWARE[language]["recommended"]
    directory = str(target["directory"])
    port = int(target["port"])
    return {
        "id": language,
        "directory": directory,
        "framework": str(target["framework"]),
        "runtime": str(target["runtime"]),
        "toolchain": str(target["toolchain"]),
        "port": port,
        "health_url": f"http://127.0.0.1:{port}/health",
        "minimum_hardware": {
            "cpu": minimum[0],
            "memory_gb": minimum[1],
            "disk_gb": minimum[2],
        },
        "recommended_hardware": {
            "cpu": recommended[0],
            "memory_gb": recommended[1],
            "disk_gb": recommended[2],
        },
        "verify_steps": [f"cd {directory}", "make test"],
        "run_steps": [f"cd {directory}", "make run", f"curl --fail http://127.0.0.1:{port}/health"],
    }


def _aggregate(request: SynthesisRequest) -> dict[str, Any]:
    languages = [target.language for target in request.targets]
    minimum = [_HARDWARE[language]["minimum"] for language in languages]
    recommended = [_HARDWARE[language]["recommended"] for language in languages]
    return {
        "sequential_minimum": {
            "cpu": max(item[0] for item in minimum),
            "memory_gb": max(item[1] for item in minimum),
            "disk_gb": sum(item[2] for item in minimum),
        },
        "sequential_recommended": {
            "cpu": max(item[0] for item in recommended),
            "memory_gb": max(item[1] for item in recommended),
            "disk_gb": sum(item[2] for item in recommended),
        },
        "concurrent_recommended": {
            "cpu": sum(item[0] for item in recommended),
            "memory_gb": sum(item[1] for item in recommended),
            "disk_gb": sum(item[2] for item in recommended),
        },
        "note": "磁盘按所有已选工程、依赖缓存和构建产物合计；并发值按同时构建并运行全部目标估算。",
    }


def _local_markdown(request: SynthesisRequest, profiles: list[dict[str, Any]], aggregate: dict[str, Any]) -> str:
    target_sections = []
    for profile in profiles:
        hardware = _HARDWARE[str(profile["id"])]
        target_sections.append(
            clean(
                f"""
                ## {str(profile["id"]).upper()} · {profile["framework"]} {profile["runtime"]}

                - 精确工具链：`{profile["toolchain"]}`
                - 最低硬件：{_hardware_text(hardware["minimum"])}
                - 推荐硬件：{_hardware_text(hardware["recommended"])}
                - 工程目录：`{profile["directory"]}`；端口：`{profile["port"]}`

                ```bash
                cd {profile["directory"]}
                make test
                make run
                # 新终端执行
                curl --fail {profile["health_url"]}
                ```
                """
            )
        )
    sequential = aggregate["sequential_recommended"]
    concurrent = aggregate["concurrent_recommended"]
    return clean(
        f"""
        # 本地运行配置与步骤

        本文对应生成时已批准的精确目标集合。所有外部运行证据当前为 `NOT_RUN`；
        请勿把文件生成、依赖安装或一次本地启动表述为生产验收。

        ## 整体硬件建议

        - 逐个构建/运行：{sequential["cpu"]} vCPU / {sequential["memory_gb"]} GB RAM /
          {sequential["disk_gb"]} GB 可用磁盘。
        - 同时构建并运行全部目标：{concurrent["cpu"]} vCPU /
          {concurrent["memory_gb"]} GB RAM / {concurrent["disk_gb"]} GB 可用磁盘。
        - 操作系统：当前受支持的 macOS 或 Linux；Windows 建议使用 WSL2。
        - 公共软件：Git、Make、curl；容器路径另需 rootless Docker 或 Podman 与 Compose。
        - 数据配置：`{request.persistence}`；认证配置：`{request.auth_mode}`。

        ## 通用步骤

        1. 解压到不含凭证的本地目录，先阅读 `requirements/approved-request.json`。
        2. 按下方目标安装**精确版本**工具链，并在终端确认版本。
        3. 在每个目标目录执行 `make test`，任何失败都停止。
        4. 执行 `make run`，再从另一个终端访问对应 `/health`。
        5. 仅在镜像基础层摘要已由交付策略批准后使用 `docker compose up --build`。
        6. PostgreSQL/JWT/OIDC 配置必须使用文件型 Secret，不把凭证写入仓库或命令历史。

        {"".join(target_sections)}

        ## 完成标准

        本地完成仅表示：精确工具链可用、测试通过、服务绑定回环地址且健康检查成功。
        数据迁移、租户隔离、恢复演练、容量、SLO、云端身份和生产部署仍需独立证据。
        """
    )


def _cloud_markdown(request: SynthesisRequest, profiles: list[dict[str, Any]]) -> str:
    target_rows = "\n".join(
        f"| {profile['id']} | `{profile['directory']}/Dockerfile` | {profile['port']} | `/health` |"
        for profile in profiles
    )
    database_step = (
        "7. PostgreSQL 配置优先使用同区域 Cloud SQL for PostgreSQL；设置连接池和实例上限，"
        "Secret 只通过 Secret Manager 挂载文件，并先执行迁移/回滚演练。"
        if request.requires_database
        else "7. 当前为内存 Starter；扩缩容会产生多副本状态分叉，生产前必须改用外置持久化。"
    )
    auth_step = (
        "8. 为 JWT/OIDC 配置精确 issuer、audience 与 Secret/JWKS 版本，权限缺失时默认拒绝。"
        if request.auth_mode != "none"
        else "8. 当前没有应用认证，只允许私有服务或受控开发环境；不得直接开放公网。"
    )
    return clean(
        f"""
        # 云端部署平台与推荐配置

        当前状态：`CONFIGURATION_REQUIRED`；外部部署、恢复和认证证据：`NOT_RUN`。
        本文是可执行前的配置指导，不代表 ELMOS 已访问云账号或完成部署。

        ## 可选平台

        | 平台 | 建议 | 适用场景 |
        |---|---|---|
        | Google Cloud Run | **推荐** | 无状态 HTTP API、希望使用托管修订和按请求伸缩 |
        | Azure Container Apps | 可选 | 已使用 Azure Managed Identity、Key Vault 与 Azure Database |
        | AWS ECS on Fargate | 可选 | 已使用 ECR、IAM、VPC、ALB 与 RDS |
        | GKE / EKS / AKS | 条件选择 | 已有 Kubernetes 平台团队、准入策略、观测与升级能力 |

        Vercel 适合单独部署 Next.js 前端；本生成包中的八类后端服务不把 Vercel
        作为通用默认运行平台。

        ## 推荐：Google Cloud Run

        推荐理由：这些目标均提供容器和 HTTP 健康边界，Cloud Run 可以减少单服务的
        集群运维。数据库、身份、网络、成本与恢复仍需项目负责人审阅。

        ### 必填配置

        - `CLOUD_PROJECT_ID`、`CLOUD_REGION`、`SERVICE_NAME`
        - 专用运行时 Service Account（不得使用 Owner/Editor）
        - Artifact Registry 仓库和**精确镜像摘要** `sha256:...`
        - CPU、内存、并发、最小/最大实例与允许的 ingress
        - 每个 Secret 的名称和不可变版本；禁止 `latest`
        - 数据库、DNS、告警、预算与回滚负责人

        ### 详细步骤

        1. 登录受控账号并确认项目、区域、计费、数据驻留与操作授权。
        2. 启用 Cloud Run、Artifact Registry、Cloud Build、Secret Manager；
           使用数据库时再启用 Cloud SQL Admin API。
        3. 创建区域性 Artifact Registry 和专用运行时 Service Account，只授予实际所需角色。
        4. 在目标目录构建并推送镜像，读取远端 `sha256`；部署命令必须使用
           `REGION-docker.pkg.dev/PROJECT/REPOSITORY/IMAGE@sha256:...`。
        5. 用 Secret Manager 文件挂载传递数据库/JWT/OIDC Secret，并固定 Secret 版本。
        6. 部署时默认 `--no-allow-unauthenticated`，设置端口、CPU、内存、并发、
           `--min`/`--max` 实例与专用 Service Account。
        {database_step}
        {auth_step}
        9. 从有权限的调用方执行 `/health`、认证负例、CRUD 和并发冒烟；保存修订、
           镜像摘要、配置和日志证据。
        10. 先用流量切换回上一不可变修订完成回滚，再删除失败修订；
            项目结束时删除服务、镜像、未使用 Secret、数据库和网络资源并复核账单。

        ### 目标映射

        | 目标 | Dockerfile | 容器端口 | 健康路径 |
        |---|---|---:|---|
        {target_rows}

        ### 命令模板（补齐后逐条审阅）

        ```bash
        export CLOUD_PROJECT_ID="REQUIRED"
        export CLOUD_REGION="REQUIRED"
        export ARTIFACT_REPOSITORY="REQUIRED"
        export SERVICE_NAME="REQUIRED"
        export RUNTIME_SERVICE_ACCOUNT="REQUIRED"
        export IMAGE_NAME="REQUIRED"

        gcloud config set project "$CLOUD_PROJECT_ID"
        gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
          cloudbuild.googleapis.com secretmanager.googleapis.com
        gcloud artifacts repositories create "$ARTIFACT_REPOSITORY" \
          --repository-format=docker --location="$CLOUD_REGION"
        gcloud builds submit --tag \
          "$CLOUD_REGION-docker.pkg.dev/$CLOUD_PROJECT_ID/$ARTIFACT_REPOSITORY/$IMAGE_NAME:candidate"
        IMAGE_DIGEST="$(gcloud artifacts docker images describe \
          "$CLOUD_REGION-docker.pkg.dev/$CLOUD_PROJECT_ID/$ARTIFACT_REPOSITORY/$IMAGE_NAME:candidate" \
          --format='value(image_summary.digest)')"
        test -n "$IMAGE_DIGEST"
        gcloud run deploy "$SERVICE_NAME" \
          --region="$CLOUD_REGION" \
          --image="$CLOUD_REGION-docker.pkg.dev/$CLOUD_PROJECT_ID/$ARTIFACT_REPOSITORY/$IMAGE_NAME@$IMAGE_DIGEST" \
          --service-account="$RUNTIME_SERVICE_ACCOUNT" \
          --port=REQUIRED --cpu=REQUIRED --memory=REQUIRED \
          --concurrency=REQUIRED --min=REQUIRED --max=REQUIRED \
          --no-allow-unauthenticated
        ```

        Secret 挂载示例：`--update-secrets=/run/secrets/database-url=database-url:REQUIRED_VERSION`。
        运行时环境变量应引用文件路径，例如
        `ELMOS_DATABASE_URL_FILE=/run/secrets/database-url`，不得直接携带 Secret 值。
        """
    )


def render_deployment_guidance(request: SynthesisRequest) -> dict[str, str]:
    profiles = [_target_profile(target.language) for target in request.targets]
    aggregate = _aggregate(request)
    contract = {
        "schema_version": "1.0.0",
        "kind": "elmos.deployment-guidance",
        "status": "CONFIGURATION_REQUIRED",
        "external_execution_evidence": "NOT_RUN",
        "production_delivery_status": "NOT_RUN",
        "project": {
            "name": request.project_name,
            "persistence": request.persistence,
            "auth_mode": request.auth_mode,
        },
        "local": {
            "aggregate_hardware": aggregate,
            "targets": profiles,
        },
        "cloud": {
            "recommended_platform": "google-cloud-run",
            "options": _CLOUD_OPTIONS,
            "required_before_apply": [
                "approved cloud project, region and billing owner",
                "least-privilege runtime service account",
                "content-addressed image digest",
                "immutable Secret versions",
                "capacity, ingress, database, rollback and cleanup decisions",
            ],
            "apply_status": "NOT_RUN",
        },
    }
    return {
        "docs/LOCAL_RUN.md": _local_markdown(request, profiles, aggregate),
        "docs/CLOUD_DEPLOYMENT.md": _cloud_markdown(request, profiles),
        "deploy/deployment-options.json": json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    }
