const { createHandPortComponent } = require("../../runtime/hand-port-runtime");

Component(createHandPortComponent({
  "schemaVersion": "1.0",
  "componentName": "PlaygroundWorkspace",
  "title": "AST 拓扑与数据流",
  "role": "workbench",
  "source": {
    "file": "app/playground/PlaygroundWorkspace.tsx",
    "componentName": "PlaygroundWorkspace",
    "sha256": "sha256:044932f80cf783ca91439b29611dab173589fb4c1915e450eeecfd9a6b2da868",
    "range": {
      "start": 1307,
      "end": 16295
    }
  },
  "blocker": {
    "reasonCode": "CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL",
    "reason": "state \"sourceCode\" requires a primitive literal initializer",
    "category": "effects-and-resources"
  },
  "props": [],
  "states": [
    {
      "name": "sourceLang",
      "type": "string"
    },
    {
      "name": "targetLang",
      "type": "string"
    },
    {
      "name": "sourceCode",
      "type": "string"
    },
    {
      "name": "isProcessing",
      "type": "boolean"
    },
    {
      "name": "activeTab",
      "type": "\"code\" | \"ast\" | \"lean4\" | \"pr_daemon\""
    },
    {
      "name": "proofVerified",
      "type": "boolean"
    }
  ],
  "hooks": [
    "useState",
    "useMemo"
  ],
  "resources": [],
  "apiPaths": [],
  "labels": [
    "AST 拓扑与数据流",
    "Action Cache: CAS Enabled",
    "C# (.NET 9 / Modern)",
    "C# (.NET Core)",
    "COBOL (Mainframe / IBM)",
    "Canonical Type Algebra",
    "Classes: 1, Methods: 2, StateVars: 1",
    "Control Flow & Effect Graph",
    "Cyclomatic complexity: 3, Branches verified",
    "Dafny 4.4.0",
    "Dafny 严密方法契约 (.dfy)",
    "ELMOS 检测到 1 项过时同步集合规则违规（ELMOS-RULE-JAVA-001），已自动为您生成并推送到 `elmos-fix/pr-142` 分支。",
    "Git PR 自愈智能体模拟演练 (Webhook Simulator)",
    "Git PR 自愈演练",
    "Go (1.23 / Cloud-Native)",
    "Graph: Acyclic Transformation DAG",
    "Interactive Code & Proof Sandbox v3.0.0",
    "Java (Spring / Enterprise)",
    "Lean 4 / Dafny 定理凭证",
    "Lean 4 Theorem Checker",
    "Lean 4 形式化定理规格 (.lean)",
    "Lean 4.8.0 Kernel",
    "Lines:",
    "Machine proof certified with tactic 'omega'"
  ],
  "adapters": [
    "wechat-effect-resource-lifecycle-v1",
    "wechat-plain-collection-projection-v1",
    "wechat-typed-state-decoder-v1"
  ],
  "obligations": [
    "PlaygroundWorkspace:source-blocker"
  ],
  "irDigest": "sha256:bf0c53646c91354a607e4bcb8c71803231b8078cc083ac0f5536d9004a8c3223"
}));
