# Project Generation & DDD Architecture Validator (业务线 5)

Multi-language microservice project generator (Go & Python FastAPI), cloud-native Kubernetes deployment manifest generator, and static DDD architectural constraint validator.

---

## 核心特性 (Features)

1. **Go 微服务 DDD 骨架生成器 (Go Microservice Generator)**
   - 遵循严格的 DDD 四层分层架构（Domain / Application / Infrastructure / Interfaces）。
   - 包含优雅停机、结构化日志（`log/slog`）、OpenTelemetry 分布式追踪与韧性保护机制。
   - 零外部网络依赖，生成即具备完整的单元测试并可通过本地 `go build ./...` 与 `go test ./...`。

2. **Python (FastAPI) 微服务 DDD 骨架生成器 (Python Microservice Generator)**
   - 基于现代 FastAPI 与 Pydantic v2 构建 DDD 规范架构。
   - 内置异步生命周期管理（lifespan）、数据库连接池抽象、RFC 7807 统一错误响应。
   - 完备的健康探测端点（`/healthz`、`/readyz`、`/livez`）与 Prometheus 指标抓取接口（`/metrics`）。
   - 完整的 pytest 单元与集成测试套件。

3. **云原生 Kubernetes & Helm 清单生成器 (Cloud-Native Manifests Generator)**
   - **Base**：标准化 Deployment、Service、ConfigMap、Secret、HPA、Ingress 及 Kustomization。
   - **Overlays**：支持 `dev`（单副本调试）、`staging`（预发布校验）、`prod`（高可用拓扑与亲和性策略）。
   - **Helm Chart**：完备的生产级参数化 Chart，支持 `helm lint` 与 `helm template` 一键渲染。

4. **DDD 架构约束静态验证器 (DDD Static Constraint Validator)**
   - 双引擎驱动（Go AST 引擎与 Python AST 语法树引擎）。
   - 静态扫描源码抽象语法树，严格拦截分层穿透违规（如 Domain 依赖外层、Application 依赖 Infrastructure 等）。
   - **深度反射拦截**：全面拦截动态导入（`importlib.import_module` 与 `__import__` 运行时违规走私）。

---

## CLI 命令与使用指南 (CLI Usage)

双模支持：既可通过 Go 编译二进制调用，也可直接通过 Python 命令行调用，参数完全对称。

### 1. Go 原生命令行 (`bin/project-gen`)

```bash
# 编译二进制工具
make build

# 快速生成 Go DDD 微服务（支持 generate 或 new）
./bin/project-gen new --lang go --name order-service --module github.com/example/order-service --port 8080 --out ./output/order-service

# 快速生成 Python FastAPI DDD 微服务
./bin/project-gen new --lang python --name user-service --port 8000 --out ./output/user-service

# 一键生成 Kubernetes 发布清单与 Helm Chart (k8s 快捷子命令)
./bin/project-gen k8s --name order-service --port 8080 --replicas 3 --out ./output/k8s-order

# 执行 DDD 分层架构静态校验（支持 --dir、--path 或位置参数）
./bin/project-gen validate --path ./output/order-service --arch ddd
./bin/project-gen validate ./output/user-service --format json
```

### 2. Python 命令行 (`project_generation/cli.py`)

```bash
# 通过 uv / python 执行
python3 -m project_generation.cli new --lang go --name order-service --out ./output/order-service
python3 -m project_generation.cli new --lang python --name user-service --out ./output/user-service
python3 -m project_generation.cli k8s --name order-service --out ./output/k8s-order

# 执行 DDD 架构约束验证
python3 -m project_generation.cli validate --path ./output/order-service
```

---

## 参数参考 (Flag Reference)

### `generate` / `new` 命令

| 参数标志 (Flags) | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| `-lang`, `--language` | string | `go` | 目标类型：`go`、`python` 或 `k8s` |
| `-name`, `--name` | string | `my-service` | 工程 / 微服务名称 |
| `-module`, `--module` | string | 与 name 相同 | Go 模块路径 (如 `github.com/org/svc`) |
| `-output`, `--out` | string | `./<name>` | 输出目标目录路径 |
| `-port`, `--port` | string | `8080` | HTTP 服务监听端口 |
| `-grpc-port`, `--grpc-port` | string | `9090` | gRPC 监听端口（Go 服务） |
| `-database`, `--database` | string | `postgres` | 数据存储层选型（postgres/mysql 等） |
| `-template-dir` | string | `""` | 自定义模板目录（留空自动回溯查找） |
| `--with-telemetry` | bool | `true` | 是否启用 OpenTelemetry 遥测中间件 |
| `--with-resilience` | bool | `true` | 是否启用熔断器与重试韧性机制 |

### `validate` 命令

| 参数标志 (Flags) | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| `path` (位置参数) | string | `.` | 待校验的代码目录路径 |
| `-dir`, `-path`, `--path` | string | `.` | 待校验的代码目录路径 |
| `-format`, `--format` | string | `text` | 输出报告格式：`text` 或 `json` |
| `-arch`, `--arch` | string | `ddd` | 架构模式（目前严格校验 DDD 四层） |

---

## 测试与质量验证 (Testing & Verification)

```bash
# 运行全部验证套件（包含 Go 单元测试、Python pytest、以及端到端生成测试）
make test

# 单独运行 Go 测试
make test-go

# 单独运行 Python 测试
make test-py
```
