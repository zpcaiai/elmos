# Batch 106 — Polyglot Ephemeral Preview Runtime

将Java、Python、.NET和Go项目统一包装为OCI工作负载，在隔离沙箱中提供限时HTTP/页面预览并可靠销毁。

## Skill inventory

| ID | Skill | Primary output |
|---|---|---|
| B106-S01 | `polyglot-project-runtime-detector` | RuntimeDetectionResult, service candidates |
| B106-S02 | `runtime-manifest-generator` | RuntimeManifest, manifest digest |
| B106-S03 | `runtime-manifest-schema-validator` | ManifestValidationResult, normalized manifest |
| B106-S04 | `java-preview-runtime-adapter` | JavaBuildSpec, JavaRunSpec |
| B106-S05 | `python-preview-runtime-adapter` | PythonBuildSpec, PythonRunSpec |
| B106-S06 | `dotnet-preview-runtime-adapter` | DotnetBuildSpec, DotnetRunSpec |
| B106-S07 | `go-preview-runtime-adapter` | GoBuildSpec, GoRunSpec |
| B106-S08 | `oci-build-artifact-normalizer` | OCIImageRef, SBOM |
| B106-S09 | `preview-image-cache-and-snapshot-manager` | CacheEntry, SandboxSnapshot |
| B106-S10 | `ephemeral-sandbox-instance-provisioner` | SandboxInstance, lease token |
| B106-S11 | `preview-port-exposure-controller` | PublicEndpoint, access token |
| B106-S12 | `readiness-and-startup-state-machine` | RunStateTransitions, ready decision |
| B106-S13 | `ready-triggered-ttl-controller` | TTLLease, expiration events |
| B106-S14 | `runtime-log-and-event-stream` | LiveEventStream, log artifact |
| B106-S15 | `ttl-reaper-and-resource-cleaner` | CleanupReceipt, orphan report |
| B106-S16 | `preview-runtime-provider-abstraction` | SandboxProvider SPI, provider capability matrix |

## Batch closure

Batch 106 只有在 `preview-runtime-provider-abstraction` 的保守Gate由真实Evidence通过后才关闭。静态包校验不代表目标ELMOS代码已实现。
