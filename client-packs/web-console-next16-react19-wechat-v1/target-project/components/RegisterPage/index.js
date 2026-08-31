const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "RegisterPage",
  "title": "//",
  "role": "shell",
  "source": {
    "file": "app/register/page.tsx",
    "componentName": "RegisterPage",
    "sha256": "sha256:7a3d403961ce8e8ed01cd9a6fcb260bd95c350e40485c04f747ccf75864c97cd",
    "range": {
      "start": 857,
      "end": 3502
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
    "/api/auth/register"
  ],
  "labels": [
    "//",
    "/api/auth/register",
    "LOCAL DEVELOPMENT IDENTITY",
    "alert",
    "auth-card",
    "auth-error",
    "auth-form",
    "auth-links",
    "auth-not-configured",
    "auth-page",
    "button button-primary",
    "displayName",
    "email",
    "eyebrow",
    "hidden",
    "name",
    "new-password",
    "password",
    "passwordConfirmation",
    "post",
    "register-title",
    "returnTo",
    "status",
    "submit"
  ],
  "adapters": [
    "wechat-cancellable-request-v1"
  ],
  "obligations": [
    "RegisterPage:source-blocker"
  ],
  "irDigest": "sha256:f208b5e9560e7e5e91bc0196a5cb28515f5bcb2117fb49250b49f620587d6a24"
}));
