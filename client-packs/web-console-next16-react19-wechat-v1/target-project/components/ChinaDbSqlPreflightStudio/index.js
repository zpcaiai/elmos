const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "ChinaDbSqlPreflightStudio",
  "title": "/api/capabilities/database-sql",
  "role": "disclosure",
  "source": {
    "file": "app/migration/sql/ChinaDbSqlPreflightStudio.tsx",
    "componentName": "ChinaDbSqlPreflightStudio",
    "sha256": "sha256:ed319e03c4dfb31ec46e4c713ab04df4d5cb94e101181618299f26ff35fee9c8",
    "range": {
      "start": 3464,
      "end": 19739
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_TYPE",
    "reason": "state result.statements element.sourceAst has incompatible union object shapes",
    "category": "data-contracts"
  },
  "props": [],
  "states": [
    {
      "name": "capabilities",
      "type": "ChinaDbSqlCapabilities | null"
    },
    {
      "name": "fields",
      "type": "FormFields"
    },
    {
      "name": "parameters",
      "type": "ChinaDbSqlParameter[]"
    },
    {
      "name": "result",
      "type": "ChinaDbSqlPreflightResult | null"
    },
    {
      "name": "loadingCapabilities",
      "type": "inferred"
    },
    {
      "name": "busy",
      "type": "inferred"
    },
    {
      "name": "error",
      "type": "inferred"
    }
  ],
  "hooks": [
    "useState",
    "useRef",
    "useEffect",
    "useMemo"
  ],
  "resources": [
    "NETWORK"
  ],
  "apiPaths": [
    "/api/capabilities/database-sql",
    "/api/database-sql/preflight"
  ],
  "labels": [
    "/api/capabilities/database-sql",
    "/api/database-sql/preflight",
    "/migration",
    "1.0",
    "BATCH 31 · READ-ONLY SOURCE PREFLIGHT",
    "BLOCKED",
    "Blockers",
    "CHINADB_SQL_CAPABILITIES_UNAVAILABLE",
    "CHINADB_SQL_PREFLIGHT_REJECTED",
    "Charset",
    "ChinaDB SQL 只读预检",
    "ChinaDB 目标",
    "Collation",
    "Compatibility mode",
    "Content-Type",
    "Driver",
    "ERROR",
    "EXACT REQUEST",
    "Edition",
    "FAIL-CLOSED BOUNDARY",
    "FALSE",
    "KiB。SQL 只发送到同源 BFF 和受信 control-plane，不保存为草稿。",
    "NOT_CERTIFIED",
    "NOT_RUN"
  ],
  "adapters": [
    "wechat-cancellable-request-v1",
    "wechat-controlled-disclosure-v1",
    "wechat-css-module-token-map-v1",
    "wechat-effect-resource-lifecycle-v1",
    "wechat-named-slot-projection-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "ChinaDbSqlPreflightStudio:source-blocker"
  ],
  "irDigest": "sha256:affbbeca3643aea8c350afe1bb71794297357aa3e0a7b2ca04be6dae4857af05"
}));
