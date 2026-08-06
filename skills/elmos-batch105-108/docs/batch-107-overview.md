# Batch 107 — Live API, Browser and Service Validation

在真实运行实例上执行健康、OpenAPI、双版本HTTP、浏览器、截图、WebSocket和SSE验证。

## Skill inventory

| ID | Skill | Primary output |
|---|---|---|
| B107-S01 | `runtime-health-probe-runner` | HealthProbeResult, readiness evidence |
| B107-S02 | `openapi-runtime-discovery` | RuntimeOpenAPI, discovery trace |
| B107-S03 | `openapi-breaking-change-gate` | OpenAPIDiff, breaking-change decision |
| B107-S04 | `dual-version-api-replay` | DualReplayResult, response deltas |
| B107-S05 | `http-scenario-suite-generator` | HTTPScenarioSuite, coverage map |
| B107-S06 | `newman-runtime-regression-runner` | NewmanBeforeAfter, assertion delta |
| B107-S07 | `business-api-invariant-oracle` | InvariantSuite, InvariantResults |
| B107-S08 | `routing-and-trailing-slash-compatibility` | RoutingCompatibilityResult, route deltas |
| B107-S09 | `browser-preview-launcher` | BrowserSession, page navigation trace |
| B107-S10 | `browser-console-and-network-gate` | BrowserErrorReport, browser gate decision |
| B107-S11 | `page-semantic-assertion-runner` | SemanticAssertionResults, accessibility snapshots |
| B107-S12 | `desktop-and-mobile-screenshot-capture` | ScreenshotArtifacts, visual metadata |
| B107-S13 | `frontend-runtime-differential-verifier` | FrontendRuntimeDiff, semantic/visual deltas |
| B107-S14 | `websocket-sse-and-streaming-verifier` | StreamingValidationResult, protocol traces |
| B107-S15 | `runtime-service-validation-evidence-assembler` | LiveValidationBundle, evidence index |
| B107-S16 | `live-service-equivalence-gate` | LiveServiceDecision, capability claims |

## Batch closure

Batch 107 只有在 `live-service-equivalence-gate` 的保守Gate由真实Evidence通过后才关闭。静态包校验不代表目标ELMOS代码已实现。
