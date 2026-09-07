const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "LoginPage",
  "title": "/api/auth/login",
  "role": "shell",
  "source": {
    "file": "app/login/page.tsx",
    "componentName": "LoginPage",
    "sha256": "sha256:56c094fdf03884c2e7bfad9b1d360aa5cc1b3337ed6f2fbfc20d151a3c7c609f",
    "range": {
      "start": 930,
      "end": 3002
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
      "type": "Promise<{ error?: string; returnTo?: string }>",
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
    "auth-not-configured",
    "auth-page",
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
    "username",
    "仅限 localhost 的开发测试登录，默认账号为 test/test；生产环境永久禁用。",
    "使用企业账户登录",
    "使用本地测试账号登录",
    "密码"
  ],
  "adapters": [
    "wechat-cancellable-request-v1"
  ],
  "obligations": [
    "LoginPage:source-blocker"
  ],
  "irDigest": "sha256:4daa6201239fa52a6355352d1aead7209302bf0b80e989c1a5b3d53bf4c0f092"
}));
