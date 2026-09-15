import assert from "node:assert/strict";
import test from "node:test";

import { inventoryMiniappSource } from "../src/miniapp-inventory.js";
import {
  analyzeMiniappSource,
  buildMiniappSemanticIr,
} from "../src/miniapp-semantic-ir.js";
import { runMiniappConversion } from "../src/miniapp-skill-runtime.js";
import { conversionInput, miniappRequest } from "./miniapp-test-fixture.js";

const reactHooksFiles = [
  {
    path: "package.json",
    content: JSON.stringify({
      name: "react-hooks-miniapp-test",
      version: "1.0.0",
      dependencies: {
        react: "^18.2.0",
        "react-dom": "^18.2.0",
        "react-router-dom": "^6.20.0",
      },
    }),
  },
  {
    path: "package-lock.json",
    content: JSON.stringify({
      name: "react-hooks-miniapp-test",
      lockfileVersion: 3,
      packages: {
        "": {
          dependencies: { react: "^18.2.0", "react-dom": "^18.2.0" },
        },
        "node_modules/react": { version: "18.2.0" },
      },
    }),
  },
  {
    path: "src/App.tsx",
    content: `import React, { useState, useMemo, useCallback } from "react";

export function CounterView() {
  const [count, setCount] = useState(0);
  const doubleCount = useMemo(() => count * 2, [count]);

  const handleIncrement = useCallback(() => {
    setCount(count + 1);
  }, [count]);

  return (
    <div className="container">
      <span className="count">{count}</span>
      <span className="double">{doubleCount}</span>
      <button onClick={handleIncrement}>Increment</button>
    </div>
  );
}

export default CounterView;
`,
  },
  {
    path: "src/index.tsx",
    content: `import React from "react";
import ReactDOM from "react-dom/client";
import { CounterView } from "./App";

const root = ReactDOM.createRoot(document.getElementById("root")!);
root.render(<CounterView />);
`,
  },
  {
    path: "src/router.ts",
    content: `import { createRouter, createWebHistory } from "vue-router";
export default createRouter({
  history: createWebHistory("/"),
  routes: [{ path: "/", component: "CounterView" }],
});
`,
  },
];

test("React useMemo and useCallback are modeled in semantic IR and Page data without statement rejection", () => {
  const request = miniappRequest(reactHooksFiles, "react", ["wechat", "alipay"]);
  const inventory = inventoryMiniappSource({
    schemaVersion: "1.0",
    inventoryId: "inv-react-hooks",
    sourceRevision: request.source.revision,
    sourceSnapshotDigest: request.source.snapshotDigest,
    sourceLabelHint: "react",
    limits: request.policy.limits,
    files: reactHooksFiles,
  });

  const sources = Object.fromEntries(reactHooksFiles.map(file => [file.path, String(file.content)]));
  const analysis = analyzeMiniappSource(request, inventory, sources);

  // 1. Assert no statements unresolved finding for CounterView
  const unresolvedFindings = analysis.findings.filter(
    f => f.code === "MINIAPP_COMPONENT_STATEMENTS_UNRESOLVED" && f.message.includes("CounterView"),
  );
  assert.equal(unresolvedFindings.length, 0, "CounterView with useMemo/useCallback must not be flagged as unresolved");

  // 2. Build IR and check state modeling
  const ir = buildMiniappSemanticIr(request, inventory, analysis);
  const stateNames = ir.states.map(s => s.name);
  assert.ok(stateNames.includes("count"), "count must be modeled as state");
  assert.ok(stateNames.includes("doubleCount"), "doubleCount from useMemo must be modeled as state");

  // 3. End-to-end conversion generates project with Page script
  const run = runMiniappConversion(conversionInput(reactHooksFiles, "react", ["wechat", "alipay"]));
  const wechatProject = run.generatedProjects.find(p => p.platform === "wechat");
  assert.ok(wechatProject, "WeChat project must be generated");
  const pageFileEntry = Object.entries(wechatProject.files).find(([p, c]) => p.endsWith(".js") && c.includes("Page({"));
  assert.ok(pageFileEntry, "Generated WeChat project must include a Page script");
  assert.ok(pageFileEntry[1].includes("doubleCount"), "Page data must initialize doubleCount state");
});
