const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "AccountOrganizationStudio",
  "title": "ACCOUNT_LOAD_FAILED",
  "role": "workbench",
  "source": {
    "file": "app/account/AccountOrganizationStudio.tsx",
    "componentName": "AccountOrganizationStudio",
    "sha256": "sha256:98df93a6ef767e471a1f70f9890a74eab997411ec0f6657c8695d18967e6e76f",
    "range": {
      "start": 549,
      "end": 9997
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [
    {
      "name": "embedded",
      "type": "boolean",
      "optional": true
    }
  ],
  "states": [
    {
      "name": "organizations",
      "type": "Organization[]"
    },
    {
      "name": "selectedId",
      "type": "inferred"
    },
    {
      "name": "members",
      "type": "Member[]"
    },
    {
      "name": "name",
      "type": "inferred"
    },
    {
      "name": "region",
      "type": "inferred"
    },
    {
      "name": "inviteEmail",
      "type": "inferred"
    },
    {
      "name": "inviteRole",
      "type": "inferred"
    },
    {
      "name": "invitationToken",
      "type": "inferred"
    },
    {
      "name": "acceptToken",
      "type": "inferred"
    },
    {
      "name": "feedback",
      "type": "inferred"
    },
    {
      "name": "busy",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useAccountSession",
    "useState",
    "useCallback",
    "useEffect"
  ],
  "resources": [
    "UNKNOWN"
  ],
  "apiPaths": [],
  "labels": [
    "ACCOUNT_LOAD_FAILED",
    "ACCOUNT_REQUEST_REJECTED",
    "ADMIN",
    "BILLING",
    "Content-Type",
    "DELETE",
    "IDENTITY",
    "IDENTITY & TENANCY",
    "MAINTAINER",
    "MEMBER",
    "MEMBER_LOAD_FAILED",
    "OWNER",
    "PATCH",
    "POST",
    "VIEWER",
    "ap-southeast",
    "application/json",
    "authenticated",
    "button",
    "button ghost",
    "button primary",
    "cn-north",
    "email",
    "eu-central"
  ],
  "adapters": [
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "AccountOrganizationStudio:source-blocker"
  ],
  "irDigest": "sha256:b41764135a0fb4a2539de273f984c1eb5ab94a2a8af2acef5dd3fa4564d8617a"
}));
