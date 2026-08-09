package io.elmos.worker;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Adds deterministic, non-executing runtime and deployment guidance to every migrated project.
 * Cloud operations remain configuration-required and are never performed by the transformer.
 */
final class SpringDeploymentGuidance {
    private SpringDeploymentGuidance() {
    }

    /**
     * Route-aware handoff. The older overloads remain for the single recorded
     * 3.5.3 route, while every new edge gets target-correct local instructions.
     * A target without a repository-pinned container base is deliberately not
     * given an executable cloud Dockerfile.
     */
    static void writeTo(
            Path migratedRepository,
            String buildTool,
            SpringRouteCatalog.SpringRoute route
    ) {
        if (SpringRouteCatalog.TARGET_BOOT.equals(route.targetBoot())
                && SpringRouteCatalog.TARGET_JAVA.equals(route.targetJava())) {
            writeTo(migratedRepository, buildTool);
        } else {
            appendReadme(migratedRepository.resolve("README.md"));
            write(migratedRepository.resolve("docs/CLOUD_DEPLOYMENT.md"), """
                    # Spring Boot %s 云端部署交接

                    当前状态：`CONFIGURATION_REQUIRED`；外部执行证据：`NOT_RUN`；
                    生产交付状态：`NOT_RUN`。

                    路线 `%s` 的目标为 Spring Boot %s / Java %s。仓库尚未绑定并验证
                    与该精确目标一致的内容寻址构建镜像和运行镜像，因此本迁移不会生成或
                    覆盖 `deploy/cloud-run/Dockerfile`。请在独立云端门禁中固定镜像摘要、
                    最小权限身份、Secret 版本、数据库迁移/回滚、容量、ingress 和清理策略。
                    """.formatted(
                    route.targetBoot(), route.routeId(), route.targetBoot(), route.targetJava()));
            write(migratedRepository.resolve("deploy/cloud-run/deployment-profile.json"), """
                    {
                      "schema_version": "1.0.0",
                      "kind": "elmos.spring-cloud-deployment-guidance",
                      "status": "CONFIGURATION_REQUIRED",
                      "external_execution_evidence": "NOT_RUN",
                      "production_delivery_status": "NOT_RUN",
                      "route_id": "%s",
                      "runtime": {
                        "framework": "Spring Boot %s",
                        "java": "%s",
                        "build_tool": "%s",
                        "container_image": "NOT_PINNED",
                        "image_reference_policy": "DIGEST_REQUIRED"
                      }
                    }
                    """.formatted(route.routeId(), route.targetBoot(), route.targetJava(), buildTool));
        }
        writeRouteAwareLocalRun(migratedRepository, buildTool, route);
    }

    private static void writeRouteAwareLocalRun(
            Path migratedRepository,
            String buildTool,
            SpringRouteCatalog.SpringRoute route
    ) {
        boolean gradle = "gradle".equals(buildTool);
        String buildCommand = gradle
                ? "gradle --no-daemon build"
                : "mvn -B -ntp verify";
        String jarCommand = gradle
                ? "find build/libs -maxdepth 1 -type f -name '*.jar' | sort | head -n 1"
                : "find target -maxdepth 1 -type f -name '*.jar' ! -name '*.original' "
                    + "! -name '*-sources.jar' ! -name '*-javadoc.jar' | sort | head -n 1";
        write(migratedRepository.resolve("docs/LOCAL_RUN.md"), """
                # Spring Boot %s 本地运行与验证

                精确路线：`%s`

                - 声明源范围：%s [%s, %s)，Java %s，%s
                - 精确目标：Spring Boot %s，Java %s
                - 路线工程证据：%s；这不是客户、生产或认证证据

                ```bash
                java -version
                %s
                JAR_PATH="$(%s)"
                test -n "$JAR_PATH"
                SERVER_ADDRESS=127.0.0.1 SERVER_PORT=8080 java -jar "$JAR_PATH"
                ```

                在另一终端对声明的健康端点执行回环检查。安全身份与授权、数据库结构和数据、
                事务隔离/回滚、Kafka/Rabbit/JMS 交付语义、缓存、定时任务和外部系统仍须按
                FCM obligations 独立验证；未执行的域保持 `NOT_RUN`。
                """.formatted(
                route.targetBoot(),
                route.routeId(),
                route.sourceFamily().contractValue(),
                route.sourceBootMinInclusive(),
                route.sourceBootMaxExclusive(),
                String.join(",", route.sourceJavaVersions().stream().sorted().toList()),
                buildTool,
                route.targetBoot(),
                route.targetJava(),
                route.routeEvidence(),
                buildCommand,
                jarCommand));
    }

    static void writeTo(Path migratedRepository, String buildTool) {
        if (!"gradle".equals(buildTool)) {
            writeTo(migratedRepository);
            return;
        }
        appendReadme(migratedRepository.resolve("README.md"));
        write(migratedRepository.resolve("docs/LOCAL_RUN.md"), """
                # Spring Boot 3.5.3 本地运行配置与步骤

                本项目已从 Spring Boot 2.x / Gradle 转换为 Spring Boot 3.5.3 / Java 21 / Gradle 8.14.3。
                本地运行证据和云端部署证据互不替代；云端状态仍为 `NOT_RUN`。

                ```bash
                java -version
                gradle --version
                gradle --no-daemon build
                JAR_PATH="$(find build/libs -maxdepth 1 -type f -name '*.jar' | sort | head -n 1)"
                test -n "$JAR_PATH"
                SERVER_ADDRESS=127.0.0.1 SERVER_PORT=8080 java -jar "$JAR_PATH"
                ```

                在另一个终端执行：

                ```bash
                curl --fail http://127.0.0.1:8080/actuator/health \\
                  || curl --fail http://127.0.0.1:8080/health
                ```

                数据库迁移、身份/权限、租户隔离、生产数据、容量、恢复演练和 SLO
                仍需独立验收。
                """);
        write(migratedRepository.resolve("deploy/cloud-run/Dockerfile"), """
                FROM gradle:8.14.3-jdk21 AS build
                WORKDIR /workspace
                COPY . .
                RUN gradle --no-daemon build && \\
                    jar_path="$(find build/libs -maxdepth 1 -type f -name '*.jar' | sort | head -n 1)" && \\
                    test -n "$jar_path" && cp "$jar_path" /workspace/application.jar

                FROM eclipse-temurin:21-jre
                WORKDIR /app
                COPY --from=build --chown=10001:10001 /workspace/application.jar /app/application.jar
                USER 10001:10001
                ENV SERVER_ADDRESS=0.0.0.0
                ENV SERVER_PORT=8080
                EXPOSE 8080
                ENTRYPOINT ["java", "-jar", "/app/application.jar"]
                """);
        write(migratedRepository.resolve("deploy/cloud-run/Dockerfile.dockerignore"), """
                .git
                **/.git
                **/build
                **/.gradle
                **/.idea
                **/.vscode
                .env
                .env.*
                **/id_rsa
                **/id_ed25519
                **/*.pem
                **/*.key
                """);
    }

    static void writeTo(Path migratedRepository) {
        appendReadme(migratedRepository.resolve("README.md"));
        write(migratedRepository.resolve("docs/LOCAL_RUN.md"), """
                # Spring Boot 3.5.3 本地运行配置与步骤

                本项目已从精确路线 Spring Boot 2.7.18 / Java 17 / Maven 3.9.11
                转换为 Spring Boot 3.5.3 / Java 21 / Maven 3.9.11。
                本地运行证据和云端部署证据互不替代；云端状态仍为 `NOT_RUN`。

                ## 软硬件配置

                | 场景 | 最低配置 | 推荐配置 |
                |---|---|---|
                | 运行迁移后的项目 | 2 vCPU / 2 GB RAM / 5 GB 可用磁盘 | 4 vCPU / 4 GB RAM / 10 GB 可用磁盘 |
                | 重新执行完整迁移/双工具链验证 | 4 vCPU / 8 GB RAM / 20 GB 可用磁盘 | 8 vCPU / 16 GB RAM / 40 GB 可用磁盘 |

                - 操作系统：当前受支持的 macOS 或 Linux；Windows 建议使用 WSL2。
                - 目标运行工具链：JDK 21、Maven 3.9.11、Git、curl。
                - 仅重新验证源基线时需要 JDK 17；普通目标运行不需要保留 JDK 17。
                - 容器路径可选 rootless Docker/Podman；不得把 Docker socket 暴露给应用。

                ## 本地验证与运行

                ```bash
                java -version
                mvn -version
                mvn -B -ntp verify

                JAR_PATH="$(find target -maxdepth 1 -type f -name '*.jar' \
                  ! -name '*.original' ! -name '*-sources.jar' ! -name '*-javadoc.jar' \
                  | sort | head -n 1)"
                test -n "$JAR_PATH"
                SERVER_ADDRESS=127.0.0.1 SERVER_PORT=8080 java -jar "$JAR_PATH"
                ```

                在另一个终端执行：

                ```bash
                curl --fail http://127.0.0.1:8080/actuator/health \
                  || curl --fail http://127.0.0.1:8080/health
                ```

                ## 本地完成标准

                `mvn verify`、回环地址启动和健康请求必须全部成功。数据库迁移、
                身份/权限、租户隔离、生产数据、容量、恢复演练和 SLO 仍需独立验收。
                """);

        write(migratedRepository.resolve("docs/CLOUD_DEPLOYMENT.md"), """
                # Spring Boot 3.5.3 云端部署平台与推荐步骤

                当前状态：`CONFIGURATION_REQUIRED`；外部执行证据：`NOT_RUN`；
                生产交付状态：`NOT_RUN`。本文不会授权或执行任何云端变更。

                ## 平台选择

                | 平台 | 建议 | 适用场景 |
                |---|---|---|
                | Google Cloud Run | **推荐** | 无状态 HTTP API，减少单服务集群运维 |
                | Azure Container Apps | 可选 | 已使用 Azure Managed Identity、Key Vault 和 Azure Database |
                | AWS ECS on Fargate | 可选 | 已使用 ECR、IAM、VPC、ALB 和 RDS |
                | GKE / EKS / AKS | 条件选择 | 已有 Kubernetes 平台团队和准入、观测、升级能力 |

                Vercel 适合单独的 Next.js 前端，不作为该 Spring Boot 后端的默认平台。

                ## 推荐平台：Google Cloud Run

                ### 必填配置

                - Cloud 项目、区域、计费和数据驻留负责人。
                - 专用运行时 Service Account，不得授予 Owner/Editor。
                - Artifact Registry 仓库和精确镜像摘要 `sha256:...`。
                - CPU、内存、并发、最小/最大实例、ingress 和调用者。
                - Secret Manager 的 Secret 名称与不可变版本，禁止使用 `latest`。
                - 数据库连接、迁移/回滚、告警、预算、DNS 和清理负责人。

                ### 详细步骤

                1. 登录受控账号，确认项目、区域、计费、数据驻留和部署授权。
                2. 启用 Cloud Run、Artifact Registry、Secret Manager；使用数据库时再启用
                   Cloud SQL Admin API。
                3. 创建区域性 Artifact Registry 和专用运行时 Service Account，仅授予实际需要的角色。
                4. 从仓库根目录使用 `deploy/cloud-run/Dockerfile` 构建并推送镜像，
                   从远端读取 `sha256`；后续部署只使用摘要。
                5. Secret 只通过 Secret Manager 文件挂载，固定版本，不进入环境变量值、日志或仓库。
                6. 部署时默认私有：`--no-allow-unauthenticated`，并设置专用身份、
                   `SERVER_ADDRESS=0.0.0.0`、`SERVER_PORT=8080`、CPU、内存、并发和实例上限。
                7. PostgreSQL 建议使用同区域 Cloud SQL for PostgreSQL 或经批准的外部托管库；
                   设置连接池与实例上限，先完成迁移和回滚演练。
                8. 从有权限的调用方执行健康、认证负例和业务冒烟；保存修订、摘要、配置与日志证据。
                9. 回滚时把流量切回上一不可变修订；清理时删除失败修订、镜像、未使用 Secret、
                   数据库和网络资源并复核账单。

                ### 命令模板

                ```bash
                export CLOUD_PROJECT_ID="REQUIRED"
                export CLOUD_REGION="REQUIRED"
                export ARTIFACT_REPOSITORY="REQUIRED"
                export SERVICE_NAME="REQUIRED"
                export RUNTIME_SERVICE_ACCOUNT="REQUIRED"
                export IMAGE_NAME="REQUIRED"

                gcloud config set project "$CLOUD_PROJECT_ID"
                gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
                  secretmanager.googleapis.com
                gcloud artifacts repositories create "$ARTIFACT_REPOSITORY" \
                  --repository-format=docker --location="$CLOUD_REGION"

                IMAGE_URI="$CLOUD_REGION-docker.pkg.dev/$CLOUD_PROJECT_ID/$ARTIFACT_REPOSITORY/$IMAGE_NAME"
                docker build --file deploy/cloud-run/Dockerfile --tag "$IMAGE_URI:candidate" .
                docker push "$IMAGE_URI:candidate"
                IMAGE_DIGEST="$(gcloud artifacts docker images describe "$IMAGE_URI:candidate" \
                  --format='value(image_summary.digest)')"
                test -n "$IMAGE_DIGEST"

                gcloud run deploy "$SERVICE_NAME" \
                  --region="$CLOUD_REGION" \
                  --image="$IMAGE_URI@$IMAGE_DIGEST" \
                  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
                  --port=8080 --cpu=REQUIRED --memory=REQUIRED \
                  --concurrency=REQUIRED --min=REQUIRED --max=REQUIRED \
                  --set-env-vars=SERVER_ADDRESS=0.0.0.0,SERVER_PORT=8080 \
                  --no-allow-unauthenticated
                ```

                数据库 Secret 挂载示例：
                `--update-secrets=/run/secrets/database-url=database-url:REQUIRED_VERSION`。
                应用必须读取文件路径，不能把 Secret 明文放入命令或环境变量。
                """);

        write(migratedRepository.resolve("deploy/cloud-run/Dockerfile"), """
                FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
                WORKDIR /workspace
                COPY . .
                RUN mvn -B -ntp verify && \
                    jar_path="$(find target -maxdepth 1 -type f -name '*.jar' \
                      ! -name '*.original' ! -name '*-sources.jar' ! -name '*-javadoc.jar' \
                      | sort | head -n 1)" && \
                    test -n "$jar_path" && cp "$jar_path" /workspace/application.jar

                FROM eclipse-temurin:21-jre@sha256:27339648ce6fc450b3b14701ba8f40141186273fc61f24d93c0e4d6b5b27c396
                WORKDIR /app
                COPY --from=build --chown=10001:10001 /workspace/application.jar /app/application.jar
                USER 10001:10001
                ENV SERVER_ADDRESS=0.0.0.0
                ENV SERVER_PORT=8080
                EXPOSE 8080
                ENTRYPOINT ["java", "-jar", "/app/application.jar"]
                """);
        write(migratedRepository.resolve("deploy/cloud-run/Dockerfile.dockerignore"), """
                .git
                **/.git
                **/target
                **/.gradle
                **/.idea
                **/.vscode
                .env
                .env.*
                **/.env
                **/.env.*
                **/id_rsa
                **/id_ed25519
                **/*.pem
                **/*.key
                """);

        write(migratedRepository.resolve("deploy/cloud-run/deployment-profile.json"), """
                {
                  "schema_version": "1.0.0",
                  "kind": "elmos.spring-cloud-deployment-guidance",
                  "status": "CONFIGURATION_REQUIRED",
                  "external_execution_evidence": "NOT_RUN",
                  "production_delivery_status": "NOT_RUN",
                  "recommended_platform": "google-cloud-run",
                  "runtime": {
                    "framework": "Spring Boot 3.5.3",
                    "java": "21",
                    "build": "Maven 3.9.11",
                    "port": 8080,
                    "health_candidates": ["/actuator/health", "/health"],
                    "container_user": "10001:10001",
                    "image_reference_policy": "DIGEST_REQUIRED"
                  },
                  "required_before_apply": [
                    "approved cloud project, region and billing owner",
                    "least-privilege runtime service account",
                    "content-addressed image digest",
                    "immutable Secret versions",
                    "capacity, ingress, database, rollback and cleanup decisions"
                  ]
                }
                """);
    }

    private static void appendReadme(Path readme) {
        String marker = "## ELMOS 本地运行与云部署交接";
        String handoff = """

                ## ELMOS 本地运行与云部署交接

                - [`docs/LOCAL_RUN.md`](docs/LOCAL_RUN.md)：精确软硬件配置、验证、启动和健康检查。
                - [`docs/CLOUD_DEPLOYMENT.md`](docs/CLOUD_DEPLOYMENT.md)：可选云平台和推荐 Cloud Run 步骤。
                - [`deploy/cloud-run/deployment-profile.json`](deploy/cloud-run/deployment-profile.json)：
                  机器可读、默认失败关闭的云配置清单。

                云端执行、恢复和认证证据仍为 `NOT_RUN`。
                """;
        try {
            String existing = Files.isRegularFile(readme)
                    ? Files.readString(readme, StandardCharsets.UTF_8)
                    : "# Migrated Spring Boot project" + System.lineSeparator();
            if (!existing.contains(marker)) {
                Files.writeString(
                        readme,
                        existing.stripTrailing() + System.lineSeparator() + handoff.strip()
                                + System.lineSeparator(),
                        StandardCharsets.UTF_8);
            }
        } catch (IOException error) {
            throw new IllegalStateException("DEPLOYMENT_GUIDANCE_README_WRITE_FAILED:" + readme, error);
        }
    }

    private static void write(Path path, String content) {
        try {
            Files.createDirectories(path.getParent());
            Files.writeString(path, content.strip() + System.lineSeparator(), StandardCharsets.UTF_8);
        } catch (IOException error) {
            throw new IllegalStateException("DEPLOYMENT_GUIDANCE_WRITE_FAILED:" + path, error);
        }
    }
}
