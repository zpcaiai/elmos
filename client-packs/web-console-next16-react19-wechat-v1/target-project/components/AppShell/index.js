const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "AppShell",
  "title": "(prefers-reduced-motion: reduce)",
  "role": "shell",
  "source": {
    "file": "app/components/AppShell.tsx",
    "componentName": "AppShell",
    "sha256": "sha256:2b3161832ec8413c9a1d2405a5ef48106612c775cc86a677d44f66d1b351762b",
    "range": {
      "start": 5118,
      "end": 21072
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    "reason": "expression kind CallExpression is outside certified-component-v1",
    "category": "effects-and-resources"
  },
  "props": [
    {
      "name": "children",
      "type": "React.ReactNode",
      "optional": false
    }
  ],
  "states": [
    {
      "name": "mobileOpen",
      "type": "inferred"
    },
    {
      "name": "commandOpen",
      "type": "inferred"
    },
    {
      "name": "commandQuery",
      "type": "inferred"
    },
    {
      "name": "commandActive",
      "type": "inferred"
    },
    {
      "name": "showBackToTop",
      "type": "inferred"
    },
    {
      "name": "telemetryEnabled",
      "type": "inferred"
    },
    {
      "name": "profileOpen",
      "type": "inferred"
    }
  ],
  "hooks": [
    "usePathname",
    "useRouter",
    "useAccountSession",
    "useUiPreferences",
    "useState",
    "useRef",
    "useMemo",
    "useEffect"
  ],
  "resources": [
    "SUBSCRIPTION",
    "UNKNOWN",
    "STORAGE"
  ],
  "apiPaths": [
    "/api/capabilities/migration"
  ],
  "labels": [
    "(prefers-reduced-motion: reduce)",
    "/account",
    "/admin",
    "/api/capabilities/migration",
    "/help",
    "Account and organizations",
    "ArrowDown",
    "ArrowUp",
    "Capability API",
    "Close navigation",
    "Close navigation overlay",
    "Control center",
    "Current tenant",
    "ELMOS",
    "EN",
    "ESC",
    "Enter",
    "Escape",
    "Fail closed",
    "Help and readiness",
    "Local contract environment",
    "Local development",
    "Mobile primary navigation",
    "No enterprise session"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-named-slot-projection-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "AppShell:source-blocker",
    "AppShell:effect-cleanup:8019"
  ],
  "irDigest": "sha256:c734628a6d1b5da16942d07832bb3b5dc50adee2e225e93b093292d390038073"
}));
