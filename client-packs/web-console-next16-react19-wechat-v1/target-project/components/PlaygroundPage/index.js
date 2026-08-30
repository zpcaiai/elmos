const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "PlaygroundPage",
  "title": "mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8",
  "role": "shell",
  "source": {
    "file": "app/playground/page.tsx",
    "componentName": "PlaygroundPage",
    "sha256": "sha256:03967bfb8666799e7040efc95c96b53fd79f418e7d98d075ff2bfbca94461b3b",
    "range": {
      "start": 281,
      "end": 485
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_SLOT",
    "reason": "<AppShell> is given children; slot projection is outside certified-component-v1 because each target evaluates it differently",
    "category": "slots-and-composition"
  },
  "props": [],
  "states": [],
  "hooks": [],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8"
  ],
  "adapters": [
    "wechat-named-slot-projection-v1"
  ],
  "obligations": [
    "PlaygroundPage:source-blocker"
  ],
  "irDigest": "sha256:729409b68f62201e286ff56f8fb014155e1e5f9c370b135ce41f82c3b242984a"
}));
