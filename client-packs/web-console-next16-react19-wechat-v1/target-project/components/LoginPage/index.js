const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "LoginPage",
  "title": "/api/auth/login",
  "role": "shell",
  "source": {
    "file": "app/login/page.tsx",
    "componentName": "LoginPage",
    "sha256": "sha256:ef1719bfed2fbc3eca9d74b8dcff37df54d309829bc7bef671900252cd8c4995",
    "range": {
      "start": 1008,
      "end": 3538
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
    "reason": "prop searchParams.then has no object fields",
    "category": "data-contracts"
  },
  "props": [
    {
      "name": "searchParams",
      "type": "Promise<{ error?: string; registered?: string; returnTo?: string }>",
      "optional": false
    }
  ],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [
    "/api/auth/login"
  ],
  "labels": [
    "/api/auth/login",
    "Enterprise identity",
    "alert",
    "auth-card",
    "auth-error",
    "auth-form",
    "auth-links",
    "auth-not-configured",
    "auth-page",
    "auth-success",
    "button button-primary",
    "current-password",
    "eyebrow",
    "hidden",
    "login-title",
    "password",
    "post",
    "returnTo",
    "status",
    "submit",
    "test",
    "text-link",
    "username",
    "仅限 localhost 的开发测试登录，默认账号为 test/test；生产环境永久禁用。"
  ],
  "adapters": [
    "wechat-cancellable-request-v1"
  ],
  "obligations": [
    "LoginPage:source-blocker"
  ],
  "irDigest": "sha256:5d0d13976a192191e46712a8a0db5ea1f6e505fe78ca96d47ce30f8a1bfce0fa"
}));
