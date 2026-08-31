const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "SpringModernizationStudio",
  "title": "/api/github-installation",
  "role": "workbench",
  "source": {
    "file": "app/spring/SpringModernizationStudio.tsx",
    "componentName": "SpringModernizationStudio",
    "sha256": "sha256:048f5c6dbf28a160dc8a797240fc28ec2bf0b24f9bd6b554dbf07b398850126d",
    "range": {
      "start": 9025,
      "end": 46056
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [
    {
      "name": "sourceMode",
      "type": "SourceMode"
    },
    {
      "name": "repositoryUrl",
      "type": "inferred"
    },
    {
      "name": "requestedRef",
      "type": "inferred"
    },
    {
      "name": "expectedCommitSha",
      "type": "inferred"
    },
    {
      "name": "snapshotId",
      "type": "inferred"
    },
    {
      "name": "materializedRelativePath",
      "type": "inferred"
    },
    {
      "name": "repositoryWorkspaceId",
      "type": "inferred"
    },
    {
      "name": "githubRepositories",
      "type": "ConnectedRepository[]"
    },
    {
      "name": "githubRepositoryId",
      "type": "inferred"
    },
    {
      "name": "githubCatalogStatus",
      "type": "RepositoryCatalog[\"status\"]"
    },
    {
      "name": "startAfterVerification",
      "type": "inferred"
    },
    {
      "name": "capability",
      "type": "Capability | null"
    },
    {
      "name": "targetSpringBoot",
      "type": "inferred"
    },
    {
      "name": "targetJava",
      "type": "inferred"
    },
    {
      "name": "capabilityError",
      "type": "inferred"
    },
    {
      "name": "run",
      "type": "Run | null"
    },
    {
      "name": "logs",
      "type": "LogResponse | null"
    },
    {
      "name": "showLogs",
      "type": "inferred"
    },
    {
      "name": "busy",
      "type": "inferred"
    },
    {
      "name": "feedback",
      "type": "inferred"
    },
    {
      "name": "feedbackKind",
      "type": "FeedbackKind"
    },
    {
      "name": "tenantId",
      "type": "inferred"
    },
    {
      "name": "actorId",
      "type": "inferred"
    },
    {
      "name": "proxyToken",
      "type": "inferred"
    },
    {
      "name": "recoveryRunId",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useAccountSession",
    "useState",
    "useMemo",
    "useEffect",
    "useCallback"
  ],
  "resources": [
    "UNKNOWN",
    "NAVIGATION",
    "STORAGE",
    "TIMER"
  ],
  "apiPaths": [
    "/api/github-installation",
    "/api/github-repositories",
    "/api/spring-upgrades",
    "/api/spring-upgrades/capabilities"
  ],
  "labels": [
    "/api/github-installation",
    "/api/github-repositories",
    "/api/spring-upgrades",
    "/api/spring-upgrades/capabilities",
    "40 位 SHA；填写后必须完全匹配",
    "ARTIFACT_INTEGRITY_MISMATCH: 下载字节与独立验证证据不一致",
    "Artifact",
    "BLOCKED",
    "BLOCKED · 不降级执行",
    "Boot",
    "Branch / Tag",
    "CANCELLED",
    "Commit",
    "DRAFT",
    "ELMOS 受控仓库工作区",
    "ENFORCED",
    "EVIDENCE-BOUND PIPELINE",
    "Engine 能力契约尚未读取；在读取到精确版本元组之前，页面不展示任何具体版本号。",
    "Engine 能力契约尚未返回路线目录；页面不会推断支持范围。",
    "FAILED",
    "FCM",
    "GITHUB_APP",
    "GITHUB_APP_INSTALL_URL_INVALID: 安装地址未通过安全校验",
    "Git 仓库 URL"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "SpringModernizationStudio:source-blocker",
    "SpringModernizationStudio:effect-cleanup:13244"
  ],
  "irDigest": "sha256:9e805c8e0ec458bdca6d4ec10d8b5318058e248de1d5613af3d9fa041e5e6160"
}));
