const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "Icon",
  "title": "0 0 24 24",
  "role": "icon",
  "source": {
    "file": "app/components/Icon.tsx",
    "componentName": "Icon",
    "sha256": "sha256:1454edb408e7acbf7febd33f67e882f87a9ab3b56666b823f3c7935fcd0cd6fa",
    "range": {
      "start": 3629,
      "end": 3982
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TAG",
    "reason": "tag \"svg\" is outside certified-component-v1",
    "category": "platform-semantics"
  },
  "props": [
    {
      "name": "className",
      "type": "string",
      "optional": true
    },
    {
      "name": "name",
      "type": "IconName",
      "optional": false
    },
    {
      "name": "size",
      "type": "number",
      "optional": true
    }
  ],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "0 0 24 24",
    "1.8",
    "currentColor",
    "none",
    "round",
    "true"
  ],
  "adapters": [
    "wechat-icon-glyph-registry-v1"
  ],
  "obligations": [
    "Icon:source-blocker"
  ],
  "irDigest": "sha256:fab50b3bd6b3e8c871ed64e999d4593eceadd92a25f765dae95d7f42c901a789"
}));
