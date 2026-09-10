const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "UiPreferencesProvider",
  "title": "light",
  "role": "provider",
  "source": {
    "file": "app/components/UiPreferencesProvider.tsx",
    "componentName": "UiPreferencesProvider",
    "sha256": "sha256:e42a90912474fce7aa4dafb5a7e0f9f6f574486aecd116d461733b81932b31bf",
    "range": {
      "start": 806,
      "end": 1950
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
    "reason": "state locale has unsupported type \"UiLocale\"",
    "category": "data-contracts"
  },
  "props": [
    {
      "name": "children",
      "type": "ReactNode",
      "optional": false
    }
  ],
  "states": [
    {
      "name": "locale",
      "type": "UiLocale"
    },
    {
      "name": "theme",
      "type": "UiTheme"
    }
  ],
  "hooks": [
    "useState",
    "useEffect",
    "useMemo"
  ],
  "resources": [
    "UNKNOWN"
  ],
  "apiPaths": [],
  "labels": [
    "light",
    "zh-CN"
  ],
  "adapters": [
    "wechat-effect-resource-lifecycle-v1",
    "wechat-named-slot-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "UiPreferencesProvider:source-blocker"
  ],
  "irDigest": "sha256:4edbff9b7b9d35799d94b85777466027744f545608f6938e4e8e5057229181ff"
}));
