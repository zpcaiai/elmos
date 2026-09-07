const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "RepositoryWorkspaceStudio",
  "title": "..",
  "role": "workbench",
  "source": {
    "file": "app/repositories/RepositoryWorkspaceStudio.tsx",
    "componentName": "RepositoryWorkspaceStudio",
    "sha256": "sha256:98ec19f726b01677cacfc578f28e60afae3a80654f9d4e54b43bbf028eea86a5",
    "range": {
      "start": 2545,
      "end": 26873
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
      "name": "accessToken",
      "type": "inferred"
    },
    {
      "name": "provider",
      "type": "Provider"
    },
    {
      "name": "cloneUrl",
      "type": "inferred"
    },
    {
      "name": "requestedRef",
      "type": "inferred"
    },
    {
      "name": "nativeRepositoryId",
      "type": "inferred"
    },
    {
      "name": "providerInstanceId",
      "type": "inferred"
    },
    {
      "name": "credentialRef",
      "type": "inferred"
    },
    {
      "name": "recoveryId",
      "type": "inferred"
    },
    {
      "name": "workspace",
      "type": "Workspace | null"
    },
    {
      "name": "selected",
      "type": "FileContent | null"
    },
    {
      "name": "editor",
      "type": "inferred"
    },
    {
      "name": "intent",
      "type": "inferred"
    },
    {
      "name": "ownerApproved",
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
      "name": "filter",
      "type": "FileCategory | \"ALL\""
    },
    {
      "name": "newPath",
      "type": "inferred"
    },
    {
      "name": "commitMessage",
      "type": "inferred"
    },
    {
      "name": "deliveryCredentialRef",
      "type": "inferred"
    },
    {
      "name": "baseBranch",
      "type": "inferred"
    },
    {
      "name": "pullRequestTitle",
      "type": "inferred"
    },
    {
      "name": "pullRequestBody",
      "type": "inferred"
    },
    {
      "name": "pullRequestKey",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useAccountSession",
    "useState",
    "useMemo",
    "useEffect"
  ],
  "resources": [
    "STORAGE"
  ],
  "apiPaths": [
    "/api/repository-workspaces"
  ],
  "labels": [
    "..",
    "/api/repository-workspaces",
    "1. 本地 Commit",
    "2. 推送受控分支",
    "3. 创建 Pull Request",
    "ALL",
    "COMPLETE",
    "Commit、Push、PR 分权执行；不自动合并或部署",
    "Content-Type",
    "Controlled delivery",
    "DELETE",
    "ELMOS: implement approved changes",
    "GENERIC_GIT",
    "GITEE",
    "GITHUB",
    "GitHub",
    "Gitee",
    "HTTPS Clone URL",
    "Implement the approved ELMOS workspace changes",
    "OTHER",
    "POST",
    "PR 创建失败。",
    "Provider 实例",
    "Repository workspace"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "RepositoryWorkspaceStudio:source-blocker",
    "RepositoryWorkspaceStudio:effect-cleanup:4425"
  ],
  "irDigest": "sha256:aceb6f65e51e1b57219e4d804813cebcd38272b6178c9c422dde8079250e7915"
}));
