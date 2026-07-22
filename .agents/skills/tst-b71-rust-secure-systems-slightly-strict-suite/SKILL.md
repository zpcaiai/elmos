---
name: tst-b71-rust-secure-systems-slightly-strict-suite
description: "Run the slightly strict test suite for Batch 71: Rust Secure Systems, covering every source Skill with positive and negative executable cases."
metadata:
  id: TB71
  source_package: Batch 66-80 Complete
  test_profile: slightly-strict
  batch: 71
  version: 1.0.0
  status: test-ready-not-run
---
    # TB71 — Batch 71 Rust Secure Systems 略严苛测试套件

    ## Objective

    对 Batch 71 的全部 12 个Source Skills执行可重放的正向、边界、负向、故障、安全和证据完整性验证。范围为：Rust、Cargo、Axum、Tokio、Serde、Unsafe、FFI/WASM、Fuzz 与发布。

    测试不得把“生成了文件”“语法可解析”或“Mock通过”冒充真实Build、Runtime或Certified。默认结果为`not-run`。

    ## Required Inputs

    - 精确的 Batch 66–80 Source Package、`manifest.json`、`SKILL_CATALOG.csv`和Source Commit/ZIP SHA-256；
    - 本Batch代表性Fixture、恶意Fixture和至少一份未参与生成的Holdout；
    - 工具链、OS、架构、Runtime、数据库、Browser/Simulator/Device/Cluster/Runner环境清单；
    - Source Skill到Case的Coverage Matrix；
    - 批准的网络、Secret、签名、云、集群和外部副作用边界。

    ## Source Skill Coverage

    | Source ID | Source Skill | Test focus | Mandatory cases |
    |---|---|---|---|
    | PG285 | `b71-rust-project-profile-detector` | detector | `B71-PG285-RUN, B71-PG285-NEG` |
| PG286 | `b71-cargo-workspace-dependency-reproducer` | reproducer | `B71-PG286-RUN, B71-PG286-NEG` |
| PG287 | `b71-rust-axum-service-generator` | generator | `B71-PG287-RUN, B71-PG287-NEG` |
| PG288 | `b71-rust-cli-generator` | generator | `B71-PG288-RUN, B71-PG288-NEG` |
| PG289 | `b71-rust-async-worker-generator` | concurrency | `B71-PG289-RUN, B71-PG289-NEG` |
| PG290 | `b71-rust-serde-contract-generator` | contract | `B71-PG290-RUN, B71-PG290-NEG` |
| PG291 | `b71-rust-ffi-wasm-extension-generator` | native | `B71-PG291-RUN, B71-PG291-NEG` |
| PG292 | `b71-rust-unsafe-boundary-review` | native | `B71-PG292-RUN, B71-PG292-NEG` |
| PG293 | `b71-rust-supply-chain-policy` | security | `B71-PG293-RUN, B71-PG293-NEG` |
| PG294 | `b71-rust-test-property-fuzz-generator` | test | `B71-PG294-RUN, B71-PG294-NEG` |
| PG295 | `b71-rust-crosscompile-release-generator` | build | `B71-PG295-RUN, B71-PG295-NEG` |
| PG296 | `b71-rust-build-run-certifier` | build | `B71-PG296-RUN, B71-PG296-NEG` |

    ## Workflow

    1. 冻结Source Package、工作区Dirty State、工具链、依赖、时钟、Random Seed、Locale、网络和外部服务。
    2. 校验本Batch每个Source Skill的Hash与Coverage Matrix一致；Hash变化时旧Evidence立即失效。
    3. 对每个Source Skill先运行正向Case，再运行负向/故障Case；不得只验证Happy Path。
    4. 在干净临时目录运行真实Parser、Linter、Compiler、Build、Test和可用Runtime；Mock只证明Mock范围。
    5. 对生成器执行首次生成、重复生成、用户修改保护、冲突和恶意输入测试。
    6. 对Reproducer执行两次Clean Build、Offline Cache和Lockfile Tamper测试。
    7. 对Gate/Certifier注入缺失、陈旧、篡改和手工伪造Evidence，确认Fail Closed。
    8. 对失败至少重放三次后再标记Flaky；保留最小反例和未裁剪原始日志。
    9. 为每个Case生成Result、Artifact Manifest、Environment Manifest、Replay命令和Evidence Digest。
    10. 运行Batch Gate；未满足的真实环境能力必须为`blocked`或`unsupported`，不得推测通过。

    ## Suggested Verification Commands

    以下命令是技术栈模板，必须记录实际命令、版本、退出码和日志：

    - `cargo fmt --check`
- `cargo clippy --all-targets --all-features -- -D warnings`
- `cargo test --all-features`
- `cargo audit`
- `cargo test --release`

    ## Mandatory Cross-Cutting Checks

    - 版本与依赖Pin、锁文件/缓存一致性和两次Clean Build可重复性；
    - Path/Template/Shell/SQL/YAML/HCL/Groovy注入与恶意文件名；
    - Secret Canary、最小权限、跨项目/租户隔离、日志脱敏；
    - 超时、取消、重试、幂等、优雅关闭、清理和失败恢复；
    - Artifact Hash、SBOM/Provenance、Source Map和Evidence防伪；
    - 声明的OS/架构/Runtime/Provider必须有真实执行证据；
    - P95/P99、资源峰值和Artifact大小变化必须可见。

    ## Slightly Strict Thresholds

    - 全部P0必须通过，零容忍项不得Waive；
    - Critical P1必须通过；普通P1通过率至少98%，仅允许有Owner和过期时间的批准Waiver；
    - P2通过率至少95%，未运行和Skipped不计通过；
    - 每个Source Skill至少一项正向和一项负向Case均有结果；
    - 两次Clean Build必须一致，或存在可审计的非确定性解释；
    - 适用时关键模块Mutation Score至少70%，整体至少60%；
    - P95不得比Baseline恶化超过10%，Artifact/Image大小不得无批准增长超过15%；
    - Flaky Case必须三次重放，Flaky率不得超过1%；
    - 不得存在Secret泄漏、越权、数据不可逆丢失、签名/Policy绕过或伪Evidence。

    ## Verification

    ```bash
    python3 scripts/test-suite-b66-80/validate_skill_bundle.py .
    python3 scripts/test-suite-b66-80/validate_test_catalog.py test-suites/batch66-80-slightly-strict/cases/catalog.json
    python3 scripts/test-suite-b66-80/validate_coverage_matrix.py test-suites/batch66-80-slightly-strict/coverage-matrix.json test-suites/batch66-80-slightly-strict/cases/catalog.json
    python3 scripts/test-suite-b66-80/validate_result_files.py test-suites/batch66-80-slightly-strict
    python3 scripts/test-suite-b66-80/run_slightly_strict_gate.py test-suites/batch66-80-slightly-strict
    ```

    ## Stop and Escalate

    - Source Skill、版本、Owner、目标平台或真实环境不明确；
    - 正向结果没有独立Oracle，或Provider/Cluster/Device声明只由Mock支持；
    - 测试将修改生产数据、真实基础设施、签名身份或高权限环境但缺少批准；
    - 出现Secret泄漏、越权、数据损坏、未授权公网出口、供应链篡改或Evidence不一致；
    - 修复需要删除测试、扩大Tolerance、自动更新Golden、放宽Policy或隐藏失败。

    ## Evidence Contract

    每项结果必须绑定Source Skill Hash、Source Commit/Package Hash、Environment Hash、Fixture Hash、实际命令和退出码、原始日志、Artifact Hash、重试/Flaky记录、失败反例、审批/Waiver和Replay命令。

    ## Definition of Done

    - 本Batch全部24项Source-specific Cases进入真实最终状态；
    - 每个Source Skill的正向和负向覆盖完整且Source Hash未漂移；
    - P0/P1/P2、零容忍、Flaky、性能和Evidence阈值按规则计算；
    - 未运行、Skipped、Mock-only和陈旧Evidence不计Pass；
    - 输出`PASS`、`CONDITIONAL`或`BLOCKED`及准确原因。

    ## Completion Report

    返回Batch范围、环境矩阵、Source-to-Test Matrix、Case结果、失败反例、Waiver、性能/资源变化、安全与供应链发现、Evidence清单及最终门禁状态。
