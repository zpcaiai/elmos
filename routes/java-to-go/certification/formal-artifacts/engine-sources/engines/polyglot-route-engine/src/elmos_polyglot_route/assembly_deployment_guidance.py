"""Local-run and cloud-publishing guidance for an assembled translation project.

The other two ELMOS business lines (Spring modernization, multi-language
project generation) both produce a runnable HTTP service, so their deployment
guidance is framed around Cloud Run: build a container, expose a health
endpoint, deploy it. An assembled polyglot-route project is not a service --
it is a compiled library of independently certified, typed pure functions
(see `assembly.py`). Framing its "cloud deployment" as a running container
would misrepresent what was actually produced. The honest equivalent for a
library is publishing a versioned package to an artifact registry, so that is
what this module documents.

Mirrors the structure and fail-closed status conventions of
`project-synthesis-engine`'s `deployment_guidance.py` (same contract shape:
local hardware/toolchain table, cloud platform options with one recommended
platform, and a machine-readable `deployment-options.json`), adapted for a
single target language and a publish-not-run workload.
"""
from __future__ import annotations

import json
from typing import Any

from .models import Language

_HARDWARE: dict[Language, dict[str, tuple[int, int, int]]] = {
    "java": {"minimum": (2, 4, 5), "recommended": (4, 8, 10)},
    "python": {"minimum": (2, 4, 4), "recommended": (4, 8, 8)},
    "csharp": {"minimum": (2, 4, 6), "recommended": (4, 8, 12)},
    "typescript": {"minimum": (2, 4, 4), "recommended": (4, 8, 8)},
}

_TOOLCHAIN_TEXT: dict[Language, str] = {
    "java": "OpenJDK 21.0.11 + Maven",
    "python": "Python 3.12.12 + setuptools",
    "csharp": ".NET SDK 10.0.301",
    "typescript": "Node.js 26.0.0 + TypeScript 5.9.2",
}

_BUILD_COMMANDS: dict[Language, list[str]] = {
    "java": ["mvn -q -DskipTests package"],
    "python": ["python -m build"],
    "csharp": ["dotnet pack polyglot-migrated-library.csproj -c Release"],
    "typescript": ["npm install", "npx tsc -p tsconfig.json"],
}

_PACKAGE_FORMAT: dict[Language, str] = {
    "java": "Maven",
    "python": "PyPI (pip)",
    "csharp": "NuGet",
    "typescript": "npm",
}

_PUBLISH_PLATFORMS = [
    {
        "id": "aws-codeartifact",
        "name": "AWS CodeArtifact",
        "status": "RECOMMENDED",
        "fit": "单一托管仓库原生支持 Maven、npm、NuGet、PyPI 四种格式，跨语言目标无需切换平台。",
        "tradeoff": "需要 AWS 账号、IAM 授权仓库和下游消费者的凭据分发。",
    },
    {
        "id": "github-packages",
        "name": "GitHub Packages",
        "status": "OPTIONAL",
        "fit": "已在 GitHub 托管源码、希望包与仓库权限一起管理；原生支持 Maven、npm、NuGet。",
        "tradeoff": "不支持 Python/PyPI 格式；Python 目标需改用其他平台。",
    },
    {
        "id": "google-artifact-registry",
        "name": "Google Artifact Registry",
        "status": "OPTIONAL",
        "fit": "已使用 GCP；原生支持 Maven、npm、Python（pip）与通用格式仓库。",
        "tradeoff": "不支持 NuGet 格式；C# 目标需改用其他平台。",
    },
    {
        "id": "azure-artifacts",
        "name": "Azure Artifacts",
        "status": "OPTIONAL",
        "fit": "已使用 Azure DevOps；原生支持 NuGet、npm、Maven、Python 与 Universal Packages。",
        "tradeoff": "免费额度有限（每组织 2 GiB），超出后按存储计费。",
    },
]


def _hardware_text(values: tuple[int, int, int]) -> str:
    cpu, memory, disk = values
    return f"{cpu} vCPU / {memory} GB RAM / {disk} GB 可用磁盘"


def _local_markdown(target_language: Language, included_unit_count: int) -> str:
    hardware = _HARDWARE[target_language]
    toolchain = _TOOLCHAIN_TEXT[target_language]
    build_commands = "\n".join(_BUILD_COMMANDS[target_language])
    return f"""# 本地构建配置与步骤

本文档对应一次真实的 `assemble_project` + `verify_assembled_project` 运行产物：
一个由 {included_unit_count} 个已通过 `typed-pure-function-v1` 剖面认证的翻译单元
组成的 {target_language} 库工程。这是一个**库**，不是一个服务——本地"运行"指的是
构建、类型检查和单元验证，不存在需要监听的端口或健康检查地址。

## 硬件建议

- 最低配置：{_hardware_text(hardware["minimum"])}
- 推荐配置：{_hardware_text(hardware["recommended"])}
- 精确工具链：`{toolchain}`（与生成该工程时 `exact_toolchain()` 强制校验的版本一致）

## 构建步骤

```bash
cd <assembled-project-directory>
{build_commands}
```

## 完成标准与限制

- 本地完成仅表示：精确工具链可用、全项目编译/类型检查通过（`assembly-manifest.json`
  中 `build_verification_status: "PASSED"`）。
- 每个翻译单元位于独立命名空间/模块下，彼此从不合并；跨单元同名声明的语义等价性
  未被验证，调用方必须按单元 ID 单独导入，不能假设可以做统一的批量导入。
- 独立验证与外部认证仍为 `NOT_RUN` / `NOT_CERTIFIED`；`assembly-manifest.json` 中
  `excluded_units` 列出的失败/跳过单元不在本工程覆盖范围内。
"""


def _cloud_markdown(target_language: Language) -> str:
    package_format = _PACKAGE_FORMAT[target_language]
    rows = "\n".join(
        f"| {platform['name']} | {platform['status']} | {platform['fit']} |" for platform in _PUBLISH_PLATFORMS
    )
    return f"""# 云端发布平台与推荐配置

当前状态：`CONFIGURATION_REQUIRED`；外部发布证据：`NOT_RUN`。
本文是发布前的配置指导，不代表 ELMOS 已访问任何云账号或已完成发布。

本工程是 {package_format} 格式的库，"云端部署"在这里指**发布到制品仓库**，
不是运行一个常驻服务；因此本文不采用 Cloud Run 式的容器部署框架。

## 可选平台

| 平台 | 建议 | 适用场景 |
|---|---|---|
{rows}

## 推荐：AWS CodeArtifact

推荐理由：CodeArtifact 在单一托管仓库中原生支持 Maven、npm、NuGet 和 PyPI 四种
格式，无论本工程的目标语言是什么，发布流程都一致，不需要为不同语言切换平台。
账号、区域、计费与访问策略仍需项目负责人审阅。

### 必填配置

- `AWS_ACCOUNT_ID`、`AWS_REGION`、`CODEARTIFACT_DOMAIN`、`CODEARTIFACT_REPOSITORY`
- 具备发布权限的最小权限 IAM 角色（禁止使用管理员凭据发布）
- 版本号策略（本工程默认版本为 `0.0.0-experimental`，正式发布前必须替换）
- 下游消费者的认证令牌获取方式（`aws codeartifact get-authorization-token`）

### 详细步骤

1. 登录受控 AWS 账号，确认账号、区域、计费与数据驻留要求。
2. 创建或复用 CodeArtifact 域和仓库：
   `aws codeartifact create-repository --domain "$CODEARTIFACT_DOMAIN" --repository "$CODEARTIFACT_REPOSITORY"`。
3. 创建仅具备 `codeartifact:PublishPackageVersion` 等最小必要权限的 IAM 角色。
4. 获取临时授权令牌：
   `aws codeartifact get-authorization-token --domain "$CODEARTIFACT_DOMAIN" --query authorizationToken --output text`。
5. 按目标格式配置本地工具指向该仓库端点（`mvn`/`npm`/`dotnet nuget`/`twine` 各自的
   仓库端点获取命令为 `aws codeartifact get-repository-endpoint`）。
6. 先发布到一个非生产用途的预发布版本号，确认下游能成功拉取并导入后，再发布正式版本号。
7. 记录发布的确切版本号、制品 sha256、发布时间和操作者，作为可追溯证据。
8. 如需下线错误发布的版本，使用 `aws codeartifact delete-package-versions`，
   不要覆盖已发布的版本号。

```bash
export AWS_ACCOUNT_ID="REQUIRED"
export AWS_REGION="REQUIRED"
export CODEARTIFACT_DOMAIN="REQUIRED"
export CODEARTIFACT_REPOSITORY="REQUIRED"

aws codeartifact get-authorization-token \\
  --domain "$CODEARTIFACT_DOMAIN" --domain-owner "$AWS_ACCOUNT_ID" \\
  --query authorizationToken --output text

aws codeartifact get-repository-endpoint \\
  --domain "$CODEARTIFACT_DOMAIN" --domain-owner "$AWS_ACCOUNT_ID" \\
  --repository "$CODEARTIFACT_REPOSITORY" --format {package_format.split()[0].lower()}
```
"""


def render_assembly_deployment_guidance(
    target_language: Language,
    included_unit_count: int,
) -> dict[str, str]:
    contract: dict[str, Any] = {
        "schema_version": "1.0.0",
        "kind": "elmos.assembly-deployment-guidance",
        "status": "CONFIGURATION_REQUIRED",
        "external_execution_evidence": "NOT_RUN",
        "artifact_kind": "library",
        "target_language": target_language,
        "included_unit_count": included_unit_count,
        "local": {
            "toolchain": _TOOLCHAIN_TEXT[target_language],
            "minimum_hardware": dict(
                zip(("cpu", "memory_gb", "disk_gb"), _HARDWARE[target_language]["minimum"], strict=True)
            ),
            "recommended_hardware": dict(
                zip(("cpu", "memory_gb", "disk_gb"), _HARDWARE[target_language]["recommended"], strict=True)
            ),
            "build_commands": _BUILD_COMMANDS[target_language],
        },
        "cloud": {
            "package_format": _PACKAGE_FORMAT[target_language],
            "recommended_platform": "aws-codeartifact",
            "options": _PUBLISH_PLATFORMS,
            "required_before_apply": [
                "approved AWS account, region and billing owner",
                "least-privilege publish-only IAM role",
                "a real (non-0.0.0-experimental) semantic version",
                "a recorded publish evidence trail (version, sha256, timestamp, operator)",
            ],
            "apply_status": "NOT_RUN",
        },
    }
    return {
        "docs/LOCAL_RUN.md": _local_markdown(target_language, included_unit_count),
        "docs/CLOUD_PUBLISHING.md": _cloud_markdown(target_language),
        "deploy/deployment-options.json": json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    }
