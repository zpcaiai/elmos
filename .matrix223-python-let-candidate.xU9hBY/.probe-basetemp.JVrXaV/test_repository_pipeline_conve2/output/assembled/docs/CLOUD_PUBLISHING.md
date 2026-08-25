# 云端发布平台与推荐配置

当前状态：`CONFIGURATION_REQUIRED`；外部发布证据：`NOT_RUN`。
本文是发布前的配置指导，不代表 ELMOS 已访问任何云账号或已完成发布。

本工程是 Maven 格式的库，"云端部署"在这里指**发布到制品仓库**，
不是运行一个常驻服务；因此本文不采用 Cloud Run 式的容器部署框架。

## 可选平台

| 平台 | 建议 | 适用场景 |
|---|---|---|
| AWS CodeArtifact | RECOMMENDED | 单一托管仓库原生支持 Maven、npm、NuGet、PyPI 四种格式，跨语言目标无需切换平台。 |
| GitHub Packages | OPTIONAL | 已在 GitHub 托管源码、希望包与仓库权限一起管理；原生支持 Maven、npm、NuGet。 |
| Google Artifact Registry | OPTIONAL | 已使用 GCP；原生支持 Maven、npm、Python（pip）与通用格式仓库。 |
| Azure Artifacts | OPTIONAL | 已使用 Azure DevOps；原生支持 NuGet、npm、Maven、Python 与 Universal Packages。 |

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

aws codeartifact get-authorization-token \
  --domain "$CODEARTIFACT_DOMAIN" --domain-owner "$AWS_ACCOUNT_ID" \
  --query authorizationToken --output text

aws codeartifact get-repository-endpoint \
  --domain "$CODEARTIFACT_DOMAIN" --domain-owner "$AWS_ACCOUNT_ID" \
  --repository "$CODEARTIFACT_REPOSITORY" --format maven
```
