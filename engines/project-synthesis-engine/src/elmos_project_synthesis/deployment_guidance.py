from __future__ import annotations

import json
from importlib.resources import files
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
        2. 执行 `make doctor`；它会先复算所有生成文件摘要，再检查本地前置条件。
        3. 按下方目标安装**精确版本**工具链，并执行 `make verify`；任何失败都停止。
        4. 执行 `make run`，或用 `make run-<language>` 选择目标；再从另一个终端访问 `/health`。
        5. 内存且无认证的 Starter 可执行 `make up && make smoke`，服务只发布到 `127.0.0.1`，
           运行网络禁止外部出口，并配置只读文件系统、能力删除、PID/CPU/内存上限和优雅停止。
        6. PostgreSQL/JWT/OIDC 配置执行目标自己的 `make run-<language>`；该本地运行器创建一次性数据库、
           文件型 Secret、迁移、身份负例和租户隔离验证。通用 Compose 会主动拒绝此配置，避免部分启动。
        7. `make down` 停止 Compose 服务；生成的本地健康性能证据位于
           `.elmos/local-smoke.json`，但仍只属于 `LOCAL_ENGINEERING`。

        {"".join(target_sections)}

        ## 完成标准

        本地完成仅表示：精确工具链可用、测试通过、服务绑定回环地址且健康检查成功。
        PostgreSQL 目标还必须完成其本地集成场景。恢复演练、代表性容量、SLO、云端身份和
        生产部署仍需独立证据；`operations/performance-budget.json` 不把健康延迟冒充业务负载结果。
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

        ### 受控的一键入口

        生成包内的 `deploy/cloud-run-control.py` 是默认入口。先复制并填写
        `deploy/cloud-run-request.example.json`，然后执行：

        ```bash
        python3 deploy/cloud-run-control.py validate --config deploy/cloud-run-request.json
        python3 deploy/cloud-run-control.py plan --config deploy/cloud-run-request.json \
          > deploy/cloud-run-plan.json
        ```

        `plan` 不访问云端。实际部署使用 `deploy --execute`，还必须提供独立审批人签发的、
        与计划中 `config_digest`、项目、区域、服务和动作完全匹配且未过期的授权 JSON。
        控制器先部署不接流量的候选修订，完成私有身份 `/health` 检查后才切换流量；
        `rollback` 和 `destroy` 需要各自独立授权，并输出 JSON 回执。

        复制 `deploy/cloud-run-authorization.example.json`，由外部受控工作流完成审批人身份验证、
        填入计划摘要和有效期并把 `approved` 改为 `true` 后，可用一个命令执行：

        ```bash
        python3 deploy/cloud-run-control.py deploy \
          --config deploy/cloud-run-request.json \
          --execute \
          --authorization deploy/cloud-run-deploy-authorization.json \
          --executor user:cloud-operator \
          --receipt deploy/evidence/cloud-run-deploy-receipt.json
        ```

        授权 JSON 中的身份是外部工作流断言；控制器不把自填字符串当作身份认证证据。

        ### 底层命令模板（补齐后逐条审阅）

        以下命令用于解释控制器行为，不建议直接复制绕过审批与回执。

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
    cloud_secrets: list[dict[str, str]] = []
    cloud_environment = {
        "APP_ENV": "production",
        "APP_NAME": request.project_name,
    }
    if request.requires_database:
        cloud_secrets.append(
            {"mount_path": "/run/secrets/database-url", "name": "database-url", "version": "1"}
        )
        cloud_environment["ELMOS_DATABASE_URL_FILE"] = "/run/secrets/database-url"
    if request.auth_mode != "none":
        cloud_environment.update(
            {
                "ELMOS_AUTH_AUDIENCE": request.project_name,
                "ELMOS_AUTH_ISSUER": "https://replace-issuer.invalid/",
            }
        )
    if request.auth_mode == "jwt":
        cloud_secrets.append(
            {"mount_path": "/run/secrets/jwt-hmac-secret", "name": "jwt-hmac-secret", "version": "1"}
        )
        cloud_environment["ELMOS_JWT_HMAC_SECRET_FILE"] = "/run/secrets/jwt-hmac-secret"  # noqa: S105
    elif request.auth_mode == "oidc":
        cloud_secrets.append(
            {"mount_path": "/run/secrets/oidc-jwks", "name": "oidc-jwks", "version": "1"}
        )
        cloud_environment["ELMOS_OIDC_JWKS_FILE"] = "/run/secrets/oidc-jwks"
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
            "one_command_controller": "scripts/projectctl.py",
            "commands": {
                "doctor": "make doctor",
                "verify": "make verify",
                "run_first_target": "make run",
                "compose_up": "make up",
                "smoke": "make smoke",
                "compose_down": "make down",
            },
            "compose_profile": (
                "SUPPORTED_LOCAL_ENGINEERING"
                if request.persistence == "in-memory" and request.auth_mode == "none"
                else "BLOCKED_USE_TARGET_NATIVE_RUNTIME"
            ),
            "network_exposure": "127.0.0.1-only",
            "runtime_network": "internal-default-deny-egress",
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
        "deploy/cloud-run-control.py": (
            files("elmos_project_synthesis")
            .joinpath("cloud_run_control.py")
            .read_text(encoding="utf-8")
        ),
        "deploy/cloud-run-request.example.json": json.dumps(
            {
                "schema_version": 1,
                "project_id": "replace-project-id",
                "region": "asia-east1",
                "service_name": request.project_name,
                "release_id": "replace-release",
                "image": (
                    "asia-east1-docker.pkg.dev/replace-project-id/replace-repository/"
                    f"{request.project_name}@sha256:" + "0" * 64
                ),
                "runtime_service_account": (
                    f"{request.project_name}-runtime@replace-project-id.iam.gserviceaccount.com"
                ),
                "port": profiles[0]["port"],
                "cpu": "1",
                "memory": "512Mi",
                "concurrency": 40,
                "min_instances": 0,
                "max_instances": 10,
                "timeout_seconds": 300,
                "ingress": "internal",
                "health": {
                    "path": "/health",
                    "expected_json": {"service": request.project_name, "status": "UP"},
                },
                "secrets": cloud_secrets,
                "environment": cloud_environment,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        "deploy/cloud-run-authorization.example.json": json.dumps(
            {
                "schema_version": 1,
                "approved": False,
                "action": "replace-with-deploy-rollback-or-destroy",
                "config_digest": "sha256:replace-with-plan-config-digest",
                "project_id": "replace-project-id",
                "region": "asia-east1",
                "service_name": request.project_name,
                "approver": "replace-with-authenticated-approver",
                "expires_at": "replace-with-short-lived-rfc3339-timestamp",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
    }
