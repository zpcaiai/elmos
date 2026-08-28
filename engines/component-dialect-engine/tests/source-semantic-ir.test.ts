import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";

import { ALL_FRAMEWORKS } from "../src/models";
import { captureReactSourceSemanticIR } from "../src/source-semantic-ir";
import { TARGET_ADAPTERS } from "../src/target-adapters";

const SOURCE = `
import { useEffect, useMemo, useState } from "react";
import { useExternalClient } from "@app/client";
import styles from "./Dashboard.module.css";

export function Dashboard({ children, status }: { children: React.ReactNode; status: "ready" | "blocked" }) {
  const client = useExternalClient();
  const [rows, setRows] = useState<Array<{ id: string; score: number }>>([]);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/rows", { signal: controller.signal }).then(() => client.refresh());
    return () => controller.abort();
  }, [client]);
  const byId = useMemo(() => new Map(rows.map((row) => [row.id, row])), [rows]);
  return (
    <details className={styles.panel}>
      <summary>{status}</summary>
      <table><tbody>{rows.map((row) => <tr key={row.id}><td>{row.score}</td></tr>)}</tbody></table>
      <svg aria-label="score"><path d="M0 0" /></svg>
      <Widget>{children}</Widget>
      <span>{byId.size}</span>
    </details>
  );
}
`;

function capture() {
  const sourceFile = ts.createSourceFile("Dashboard.tsx", SOURCE, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const ir = captureReactSourceSemanticIR({
    sourceFile,
    sourceFramework: "react",
    sourcePath: "src/Dashboard.tsx",
    componentName: "Dashboard",
    reasonCode: "CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION",
    reason: "external Hook and platform semantics need adapters",
  });
  if (ir === null) throw new Error("Dashboard semantic IR was not captured");
  return ir;
}

describe("blocked source semantic IR", () => {
  it("captures external Hooks, effects, data, collections, slots and platform semantics with exact ranges", () => {
    const ir = capture();
    const kinds = new Set(ir.features.map((feature) => feature.kind));
    for (const expected of [
      "EXTERNAL_HOOK", "ASYNC_EFFECT", "NETWORK_RESOURCE", "OBJECT_STATE", "MAP_COLLECTION",
      "DERIVED_COLLECTION", "SLOT_PROJECTION", "COMPONENT_COMPOSITION", "TABLE_SEMANTIC",
      "DISCLOSURE_SEMANTIC", "SVG_SEMANTIC", "CSS_MODULE",
    ] as const) expect(kinds.has(expected)).toBe(true);
    expect(ir.captureStatus).toBe("REPRESENTED");
    expect(ir.hooks).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: "useExternalClient", ownerModule: "@app/client", role: "EXTERNAL" }),
      expect.objectContaining({ name: "useEffect", role: "EFFECT", dependencyCount: 1 }),
    ]));
    expect(ir.effects).toEqual(expect.arrayContaining([
      expect.objectContaining({ resources: expect.arrayContaining(["NETWORK"]), cleanup: "PRESENT", cancellation: "PRESENT" }),
    ]));
    for (const feature of ir.features) {
      expect(feature.sourceRange.end).toBeGreaterThan(feature.sourceRange.start);
      expect(feature.sourceRange.startLine).toBeGreaterThan(0);
      expect(feature.sourceExcerpt.length).toBeLessThanOrEqual(240);
    }
    expect(ir.irDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
  });

  it("is deterministic and keeps every target on an explicit adapter/hand-port/block decision", () => {
    const first = capture();
    const second = capture();
    expect(second.irDigest).toBe(first.irDigest);
    expect(Object.keys(first.targetPlans).sort()).toEqual([...ALL_FRAMEWORKS].sort());
    for (const target of ALL_FRAMEWORKS) {
      const plan = first.targetPlans[target];
      expect(plan.adapterId).toBe(TARGET_ADAPTERS[target].id);
      expect(["ADAPTER_REQUIRED", "HAND_PORTED", "BLOCKED"]).toContain(plan.disposition);
      expect(plan.decisions).toHaveLength(first.features.length);
    }
    expect(first.targetPlans.react.decisions.find((item) => item.featureKind === "TABLE_SEMANTIC")?.mode).toBe("NATIVE");
    expect(first.targetPlans.miniprogram.decisions.find((item) => item.featureKind === "TABLE_SEMANTIC")?.mode).toBe("HAND_PORTED");
    expect(first.targetPlans.react.decisions.find((item) => item.featureKind === "EXTERNAL_HOOK")?.mode).toBe("BLOCKED");
  });

  it("has a checked-in schema that requires the complete handoff contract", () => {
    const schema = JSON.parse(fs.readFileSync(path.resolve(__dirname, "..", "schemas", "source-component-semantic-ir.schema.json"), "utf8"));
    expect(schema.properties.kind.const).toBe("elmos.source-component-semantic-ir");
    expect(schema.required).toEqual(expect.arrayContaining(["features", "targetPlans", "obligations", "irDigest"]));
    expect(schema.additionalProperties).toBe(false);
  });

  it("returns null rather than inventing a component when the requested identity is absent", () => {
    const sourceFile = ts.createSourceFile("Dashboard.tsx", SOURCE, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    expect(captureReactSourceSemanticIR({
      sourceFile,
      sourceFramework: "react",
      sourcePath: "src/Dashboard.tsx",
      componentName: "Missing",
      reasonCode: "UNKNOWN",
      reason: "missing",
    })).toBeNull();
  });
});
