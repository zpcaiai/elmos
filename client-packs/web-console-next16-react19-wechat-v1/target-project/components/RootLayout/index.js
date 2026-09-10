const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "RootLayout",
  "title": "#main-content",
  "role": "shell",
  "source": {
    "file": "app/layout.tsx",
    "componentName": "RootLayout",
    "sha256": "sha256:cfb13ad9af43d647ac18d845ad0cae68f8eba9e1db71e673f2ca549fe6be5405",
    "range": {
      "start": 796,
      "end": 1251
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TAG",
    "reason": "tag \"html\" is outside certified-component-v1",
    "category": "platform-semantics"
  },
  "props": [
    {
      "name": "children",
      "type": "Readonly<{ children: React.ReactNode }>",
      "optional": false
    }
  ],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "#main-content",
    "skip-link",
    "zh-CN",
    "跳到主要内容"
  ],
  "adapters": [
    "wechat-app-page-lifecycle-v1",
    "wechat-named-slot-projection-v1"
  ],
  "obligations": [
    "RootLayout:source-blocker"
  ],
  "irDigest": "sha256:b8b916fe72119a4a4ff08d96b20d8a3bbec86a11ed299e18f72b09c1752af1e7"
}));
