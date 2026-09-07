import { buildCrossPlatformIR, classifyBlocker } from "../src/cross-platform-ir";
import { bindEvidenceObservation, createEvidenceLedger, validateEvidenceLedger } from "../src/evidence";
import { emitFromTargetAdapter, TARGET_ADAPTERS } from "../src/target-adapters";
import { ALL_FRAMEWORKS } from "../src/models";
import { parseReactComponent } from "../src/parsers/react";

const SOURCE = `
function Counter({ label, step = 1, onDone }: { label: string; step?: number; onDone: (value: number) => void }) {
  const [count, setCount] = useState<number>(0);
  return (
    <section aria-label={label}>
      <h2>{label}</h2>
      <em>{count}</em>
      <button type="button" onClick={() => { setCount(count + step); onDone(count); }}>add</button>
    </section>
  );
}
`;

describe("cross-platform semantic IR", () => {
  const component = parseReactComponent(SOURCE, "Counter.tsx");

  it("represents render, state, interaction, accessibility and target adapter semantics", () => {
    const ir = buildCrossPlatformIR(component, "react", "app/Counter.tsx");
    expect(ir.kind).toBe("elmos.cross-platform-component-ir");
    expect(ir.sourceTrace).toMatchObject({ sourceFile: "app/Counter.tsx", traceStatus: "COMPONENT_MODEL_ONLY" });
    expect(ir.sourceTrace.sourceRange).toBeNull();
    expect(ir.renderTree.kind).toBe("element");
    expect(ir.state.variables).toEqual(expect.arrayContaining([expect.objectContaining({ name: "count", ownership: "LOCAL_EPHEMERAL" })]));
    expect(ir.interactions).toEqual(expect.arrayContaining([expect.objectContaining({ event: "onClick" })]));
    expect(ir.state.transitions).toHaveLength(1);
    expect(ir.accessibility.attributes).toContain("aria-label");
    expect(Object.keys(ir.targetAdapters).sort()).toEqual([...ALL_FRAMEWORKS].sort());
    expect(ir.irDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
  });

  it("routes every target through a named adapter instead of a shared string emitter", () => {
    const ir = buildCrossPlatformIR(component, "react", "Counter.tsx");
    for (const framework of ALL_FRAMEWORKS) {
      expect(TARGET_ADAPTERS[framework].id).toBe(ir.targetAdapters[framework]?.adapterId);
      const output = emitFromTargetAdapter(ir, framework);
      expect(output.emitted ?? output.emittedFiles).toBeTruthy();
    }
  });

  it("keeps evidence requirements NOT_RUN until real artifacts are attached", () => {
    const ir = buildCrossPlatformIR(component, "react", "Counter.tsx");
    const ledger = createEvidenceLedger(ir, "vue3");
    expect(ledger.claim).toBe("NOT_CERTIFIED");
    expect(ledger.records.map((record) => record.status)).toEqual([
      "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_APPLICABLE", "NOT_RUN", "NOT_RUN",
    ]);
    expect(validateEvidenceLedger(ledger)).toEqual([]);
  });

  it("rejects fabricated successful evidence and same-producer independent review", () => {
    const ir = buildCrossPlatformIR(component, "react", "vue3");
    const ledger = createEvidenceLedger(ir, "react");
    const target = ledger.records.find((record) => record.id === "target-build");
    if (!target) throw new Error("target-build record missing");
    target.status = "PASSED";
    target.executor = "local-agent";
    expect(validateEvidenceLedger(ledger)).toContain("target-build: PASSED requires a digest-bound artifact");

    const independent = ledger.records.find((record) => record.id === "independent");
    if (!independent) throw new Error("independent record missing");
    independent.status = "PASSED";
    independent.executor = "local-agent";
    independent.verifier = "local-agent";
    independent.independent = true;
    independent.artifactPath = "evidence.json";
    independent.artifactDigest = "sha256:" + "a".repeat(64);
    expect(validateEvidenceLedger(ledger)).toContain("independent verification requires a verifier distinct from the producer");
  });

  it("binds runner artifact bytes while keeping unresolved gates and certification closed", () => {
    const ir = buildCrossPlatformIR(component, "react", "Counter.tsx");
    const ledger = createEvidenceLedger(ir, "react");
    const updated = bindEvidenceObservation(ledger, "browser", {
      status: "PASSED",
      artifactPath: "/evidence/browser.json",
      artifactContents: '{"browser":"chromium","result":"passed"}\n',
      executor: "playwright-runner",
    });
    expect(updated.records.find((record) => record.id === "browser")).toMatchObject({
      status: "PASSED",
      artifactDigest: expect.stringMatching(/^sha256:[a-f0-9]{64}$/),
      executor: "playwright-runner",
    });
    expect(updated.claim).toBe("NOT_CERTIFIED");
    expect(updated.unresolved).toContain("independent-verification");
    expect(validateEvidenceLedger(updated)).toEqual([]);
  });

  it("retains a failed runner artifact as unresolved evidence instead of discarding it", () => {
    const ir = buildCrossPlatformIR(component, "react", "Counter.tsx");
    const ledger = createEvidenceLedger(ir, "vue3");
    const updated = bindEvidenceObservation(ledger, "target-build", {
      status: "FAILED",
      artifactPath: "/evidence/target-build.log",
      artifactContents: "compiler error\n",
      executor: "target-build-runner",
    });
    expect(updated.records.find((record) => record.id === "target-build")).toMatchObject({ status: "FAILED", artifactPath: "/evidence/target-build.log" });
    expect(updated.unresolved).toContain("target-build");
    expect(validateEvidenceLedger(updated)).toEqual([]);
  });

  it("routes remaining blocker categories to explicit human work", () => {
    expect(classifyBlocker("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE")).toEqual({ category: "data-contracts", disposition: "HAND_PORTED" });
    expect(classifyBlocker("CERTIFIED_COMPONENT_UNSUPPORTED_TAG")).toEqual({ category: "platform-semantics", disposition: "HAND_PORTED" });
    expect(classifyBlocker("CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION")).toEqual({ category: "effects-and-resources", disposition: "BLOCKED" });
    expect(classifyBlocker("CERTIFIED_COMPONENT_UNSUPPORTED_SLOT")).toEqual({ category: "slots-and-composition", disposition: "HAND_PORTED" });
  });
});
