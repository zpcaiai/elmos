# 技能依赖图

依赖表示“消费其输出契约”，不表示一次任务必须执行所有分支。Orchestrator 根据实际源框架和目标平台裁剪图。

```mermaid
flowchart TD
    start([Conversion Request])
    start --> frontend_to_miniapp_orchestrator
    start --> miniapp_source_framework_detector
    miniapp_source_framework_detector --> vue_to_miniapp_analyzer
    miniapp_source_framework_detector --> react_to_miniapp_analyzer
    miniapp_source_framework_detector --> flutter_widget_semantic_reconstructor
    vue_to_miniapp_analyzer --> miniapp_semantic_ir
    react_to_miniapp_analyzer --> miniapp_semantic_ir
    flutter_widget_semantic_reconstructor --> miniapp_semantic_ir
    miniapp_semantic_ir --> miniapp_capability_registry
    miniapp_semantic_ir --> miniapp_component_mapping_engine
    miniapp_capability_registry --> miniapp_component_mapping_engine
    miniapp_semantic_ir --> miniapp_state_event_lifecycle_converter
    miniapp_component_mapping_engine --> miniapp_state_event_lifecycle_converter
    miniapp_semantic_ir --> miniapp_style_layout_converter
    miniapp_component_mapping_engine --> miniapp_style_layout_converter
    miniapp_source_framework_detector --> miniapp_third_party_dependency_migrator
    miniapp_capability_registry --> miniapp_third_party_dependency_migrator
    miniapp_component_mapping_engine --> wechat_miniapp_codegen
    miniapp_state_event_lifecycle_converter --> wechat_miniapp_codegen
    miniapp_style_layout_converter --> wechat_miniapp_codegen
    miniapp_third_party_dependency_migrator --> wechat_miniapp_codegen
    miniapp_component_mapping_engine --> alipay_miniapp_codegen
    miniapp_state_event_lifecycle_converter --> alipay_miniapp_codegen
    miniapp_style_layout_converter --> alipay_miniapp_codegen
    miniapp_third_party_dependency_migrator --> alipay_miniapp_codegen
    miniapp_component_mapping_engine --> douyin_miniapp_codegen
    miniapp_state_event_lifecycle_converter --> douyin_miniapp_codegen
    miniapp_style_layout_converter --> douyin_miniapp_codegen
    miniapp_third_party_dependency_migrator --> douyin_miniapp_codegen
    miniapp_component_mapping_engine --> xiaohongshu_miniapp_codegen
    miniapp_state_event_lifecycle_converter --> xiaohongshu_miniapp_codegen
    miniapp_style_layout_converter --> xiaohongshu_miniapp_codegen
    miniapp_third_party_dependency_migrator --> xiaohongshu_miniapp_codegen
    miniapp_capability_registry --> miniapp_commerce_social_adapter
    miniapp_capability_registry --> miniapp_privacy_permission_auditor
    miniapp_third_party_dependency_migrator --> miniapp_privacy_permission_auditor
    wechat_miniapp_codegen --> miniapp_privacy_permission_auditor
    alipay_miniapp_codegen --> miniapp_privacy_permission_auditor
    douyin_miniapp_codegen --> miniapp_privacy_permission_auditor
    xiaohongshu_miniapp_codegen --> miniapp_privacy_permission_auditor
    wechat_miniapp_codegen --> miniapp_differential_testing
    alipay_miniapp_codegen --> miniapp_differential_testing
    douyin_miniapp_codegen --> miniapp_differential_testing
    xiaohongshu_miniapp_codegen --> miniapp_differential_testing
    miniapp_style_layout_converter --> miniapp_visual_regression_testing
    miniapp_differential_testing --> miniapp_visual_regression_testing
    miniapp_differential_testing --> miniapp_auto_repair_loop
    miniapp_visual_regression_testing --> miniapp_auto_repair_loop
    miniapp_privacy_permission_auditor --> miniapp_auto_repair_loop
    miniapp_auto_repair_loop --> miniapp_ci_build_release
    miniapp_privacy_permission_auditor --> miniapp_ci_build_release
    miniapp_ci_build_release --> miniapp_migration_evidence_reporter
    miniapp_differential_testing --> miniapp_migration_evidence_reporter
    miniapp_visual_regression_testing --> miniapp_migration_evidence_reporter
    miniapp_privacy_permission_auditor --> miniapp_migration_evidence_reporter
```

## 分阶段视图

```text
Discovery
  miniapp-source-framework-detector

Source Analysis
  vue-to-miniapp-analyzer
  react-to-miniapp-analyzer
  flutter-widget-semantic-reconstructor

IR
  miniapp-semantic-ir

Planning
  miniapp-capability-registry
  miniapp-component-mapping-engine
  miniapp-state-event-lifecycle-converter
  miniapp-style-layout-converter
  miniapp-third-party-dependency-migrator
  miniapp-commerce-social-adapter

Target Generation
  wechat-miniapp-codegen
  alipay-miniapp-codegen
  douyin-miniapp-codegen
  xiaohongshu-miniapp-codegen

Validation
  miniapp-differential-testing
  miniapp-visual-regression-testing
  miniapp-privacy-permission-auditor

Repair
  miniapp-auto-repair-loop

Delivery and Evidence
  miniapp-ci-build-release
  miniapp-migration-evidence-reporter
```

## 动态裁剪规则

- 只检测到 Vue 时，不调用 React/Flutter analyzer。
- 只选择微信目标时，不执行其余三个 generator，但 capability registry 仍可报告跨平台可移植性。
- 不含商业、身份或社交能力时，commerce-social adapter 可标记不适用。
- 不执行上传/发布时，CI skill 只运行 build/preview 级别。
- 自动修复只在存在可重现 finding、回滚点和剩余重试预算时进入。
- evidence reporter 在每个阶段都可增量执行，最终执行依赖全部适用门禁。

## 无环约束

`skill-manifest.yaml` 中的 `depends_on` 必须形成 DAG。`scripts/verify_package.py` 会检测：

- 不存在的依赖；
- 自依赖；
- 环；
- 重复技能名；
- manifest 与目录不一致。

新增技能时必须同时更新 manifest、依赖图、任务文档和测试。
