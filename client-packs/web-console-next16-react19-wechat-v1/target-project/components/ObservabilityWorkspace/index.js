const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "ObservabilityWorkspace",
  "title": "128",
  "role": "workbench",
  "source": {
    "file": "app/observability/ObservabilityWorkspace.tsx",
    "componentName": "ObservabilityWorkspace",
    "sha256": "sha256:09653cd1b9253c7d7d575e1aeac4e5a399e1210fd115e04bdf28ce38b6c1cc20",
    "range": {
      "start": 1418,
      "end": 8658
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL",
    "reason": "state initializer expression kind ElementAccessExpression is not a closed literal",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [
    {
      "name": "selectedSpan",
      "type": "SpanItem"
    },
    {
      "name": "activeTab",
      "type": "\"traces\" | \"metrics\" | \"slsa\""
    }
  ],
  "hooks": [
    "useState",
    "useMemo"
  ],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "128",
    "3fa89b2c7e014d5f99238910fedcba45... (HMAC-SHA256 / Ed25519)",
    "452,900",
    "640",
    "88.4%",
    "Attributes (OpenTelemetry Attributes)",
    "Builder ID:",
    "Ed25519 Verified",
    "Hermetic Toolchains Locked:",
    "In-Toto / SLSA Level 4 密码学构建存证",
    "Lean 4.8.0, Dafny 4.4.0, Z3 4.12.2, CVC5 1.1.2",
    "OTLP v1.3 / SLSA Level 4",
    "Predicate Type:",
    "Prometheus Metrics Endpoint (`elmos telemetry metrics`)",
    "Prometheus 实时指标",
    "SLSA Level 4 密码学凭证",
    "SMT / Lean 4 定理证明放行数",
    "Scrape Status: UP",
    "Signature:",
    "Span ID",
    "Span 详情与 W3C 属性",
    "Trace Waterfall (Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736)",
    "Tree-sitter 增量解析节点数",
    "elmos_ast_nodes_parsed_total"
  ],
  "adapters": [
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "ObservabilityWorkspace:source-blocker"
  ],
  "irDigest": "sha256:b878b68d0564af9a6991321f7029e023431f185265513fb65e1ade31ac6e04a5"
}));
