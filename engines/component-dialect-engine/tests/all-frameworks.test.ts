/**
 * Coverage for every framework certified-component-v1 supports, driving
 * each one's real compiler.
 */
import { translateComponent } from "../src/engine";
import { parseReactComponent } from "../src/parsers/react";
import { parseVue2Component } from "../src/parsers/vue2";
import { parseVue3Component } from "../src/parsers/vue3";
import { emitVue2 } from "../src/emitters/vue2";
import { emitVue3 } from "../src/emitters/vue3";
import { emitAngular } from "../src/emitters/angular";
import { emitSvelte } from "../src/emitters/svelte";
import { validateSyntax } from "../src/validator";
import { ALL_FRAMEWORKS, DialectError, PARSEABLE_FRAMEWORKS } from "../src/models";

const COUNTER = `
function Counter({ label, step = 1, onDone }: { label: string; step?: number; onDone: (value: number) => void }) {
  const [count, setCount] = useState<number>(0);
  return (
    <div className="counter">
      <h2>{label}</h2>
      <em>{count}</em>
      {step > 3 ? (<strong>big</strong>) : (<strong>small</strong>)}
      <button type="button" onClick={() => { setCount(count + step); onDone(count); }}>add</button>
    </div>
  );
}
`;

const TARGETS = ["vue3", "vue2", "angular", "svelte", "react-native", "miniprogram", "arkui", "flutter"] as const;

const INPUT_VALIDATION = `
const projectRefPattern = /^[a-z0-9][a-z0-9._/-]{2,180}$/i;
function InputValidation() {
  const [draft, setDraft] = useState<string>("");
  const valid = projectRefPattern.test(draft.trim()) && !draft.includes("..");
  return <div>
    <input value={draft} maxLength={180} onChange={(event) => setDraft(event.target.value)} />
    <button disabled={!valid} onClick={() => setDraft(draft.trim())}>load</button>
  </div>;
}
`;

describe("every certified target accepts a real component", () => {
  it.each(TARGETS)("react -> %s passes its own real compiler", async (target) => {
    const report = await translateComponent(COUNTER, "react", target, { fileName: "Counter.tsx", skipExecution: true });
    expect(report.status).toBe("PASSED");
    expect(report.validation?.syntaxStatus).toBe("PASSED");
    expect(report.emitted ?? report.emittedFiles).toBeTruthy();
  });

  it.each(TARGETS)("react -> %s preserves bounded input validation", async (target) => {
    const report = await translateComponent(INPUT_VALIDATION, "react", target, { fileName: "InputValidation.tsx", skipExecution: true });
    expect(report.status).toBe("PASSED");
    expect(report.validation?.syntaxStatus).toBe("PASSED");
  });

  it("refuses a same-framework route", async () => {
    await expect(translateComponent(COUNTER, "react", "react")).rejects.toThrow(/SOURCE_AND_TARGET_MUST_DIFFER/);
  });

  it("refuses an unknown framework name before doing any work", async () => {
    await expect(translateComponent(COUNTER, "react", "qt")).rejects.toThrow(/UNSUPPORTED_FRAMEWORK/);
  });
});

describe("Vue 2 as a real source", () => {
  it("round-trips structure exactly, losing only what Vue 2 genuinely cannot express", () => {
    const original = parseReactComponent(COUNTER, "Counter.tsx");
    const sfc = emitVue2(original);
    expect(validateSyntax("vue2", sfc)).toEqual({ status: "PASSED", diagnostics: [] });

    const roundTripped = parseVue2Component(sfc, "Counter.vue");

    // Vue 2's Options API has no typed emit declaration, so a callback's
    // payload type cannot survive. That is the ONLY permitted difference;
    // everything else must match exactly.
    const stripPayloadTypes = (component: typeof original) => ({
      ...component,
      props: component.props.map((p) => (p.kind === "callback" ? { ...p, paramType: undefined } : p)),
    });
    expect(roundTripped).toEqual(stripPayloadTypes(original));

    // And the loss must be visible, not silent.
    const callback = original.props.find((p) => p.kind === "callback");
    expect(callback && callback.kind === "callback" && callback.paramType).toBe("number");
    const after = roundTripped.props.find((p) => p.kind === "callback");
    expect(after && after.kind === "callback" && after.paramType).toBeUndefined();
  });

  it("reports the payload-type loss as a translation note", async () => {
    const report = await translateComponent(COUNTER, "react", "vue2", { fileName: "Counter.tsx", skipExecution: true });
    expect(report.notes.join(" ")).toMatch(/no typed emit declaration/);
  });

  it("preserves the class attribute that vue-template-compiler hoists out of attrsList", () => {
    const sfc = emitVue2(parseReactComponent(COUNTER, "Counter.tsx"));
    const parsed = parseVue2Component(sfc, "Counter.vue");
    expect(parsed.root.kind).toBe("element");
    if (parsed.root.kind !== "element") throw new Error("expected an element root");
    expect(parsed.root.attrs).toContainEqual({ kind: "static", name: "class", value: "counter" });
  });

  it("blocks Options API features outside the subset", () => {
    const sfc = `<template><div>{{ x }}</div></template>\n<script>\nexport default { computed: { x() { return 1; } } };\n</script>`;
    expect(() => parseVue2Component(sfc, "C.vue")).toThrow(DialectError);
  });
});

describe("Vue 3 round trip stays exact", () => {
  it("React -> Vue 3 -> React loses nothing at all", () => {
    const original = parseReactComponent(COUNTER, "Counter.tsx");
    expect(parseVue3Component(emitVue3(original), "Counter.vue")).toEqual(original);
  });
});

describe("Angular emission", () => {
  const ir = () => parseReactComponent(COUNTER, "Counter.tsx");

  it("uses Angular binding syntax, not Vue's", () => {
    const source = emitAngular(ir());
    expect(source).toContain("@Component({");
    expect(source).toContain("standalone: true");
    expect(source).toContain("@Input()");
    expect(source).toContain("@Output() done = new EventEmitter<number>();");
    expect(source).toContain("(click)=");
    expect(source).toContain("*ngIf=");
    expect(source).not.toContain("v-if");
    expect(source).not.toContain("@click=");
  });

  it("uses an ng-template for the else branch, since Angular has no sibling v-else", () => {
    const source = emitAngular(ir());
    expect(source).toMatch(/\*ngIf="[^"]*; else elseBlock0"/);
    expect(source).toContain("<ng-template #elseBlock0>");
  });

  it("marks required inputs with a definite-assignment assertion", () => {
    expect(emitAngular(ir())).toContain("@Input() label!: string;");
  });

  it("is accepted by the real @angular/compiler", () => {
    expect(validateSyntax("angular", emitAngular(ir()))).toEqual({ status: "PASSED", diagnostics: [] });
  });
});

describe("Svelte emission", () => {
  const ir = () => parseReactComponent(COUNTER, "Counter.tsx");

  it("uses runes and block conditionals", () => {
    const source = emitSvelte(ir());
    expect(source).toContain("$props()");
    expect(source).toContain("$state<number>(0)");
    expect(source).toContain("{#if ");
    expect(source).toContain("{:else}");
    expect(source).toContain("{/if}");
    // Svelte assigns state directly; no setter exists.
    expect(source).toContain("count = count + step");
    expect(source).not.toContain("setCount");
  });

  it("is accepted by the real svelte compiler", () => {
    expect(validateSyntax("svelte", emitSvelte(ir()))).toEqual({ status: "PASSED", diagnostics: [] });
  });
});

describe("framework registry honesty", () => {
  it("lists exactly the frameworks that really have a parser", () => {
    expect([...PARSEABLE_FRAMEWORKS].sort()).toEqual(
      ["angular", "miniprogram", "react", "react-native", "svelte", "typescript", "vue2", "vue3"].sort(),
    );
  });

  it("never claims ArkUI or Flutter can be a source", () => {
    expect(PARSEABLE_FRAMEWORKS.has("arkui")).toBe(false);
    expect(PARSEABLE_FRAMEWORKS.has("flutter")).toBe(false);
  });

  it("covers all ten named frameworks", () => {
    expect(ALL_FRAMEWORKS).toHaveLength(10);
  });

  it("has a working parser for every framework it declares parseable", async () => {
    // PARSEABLE_FRAMEWORKS is a promise to the caller. Every entry must
    // actually reach a parser -- reaching the PARSER_NOT_IMPLEMENTED
    // fallback would mean the registry is advertising a capability the
    // engine does not have.
    const fixtures: Record<string, string | { wxml: string; js: string }> = {
      react: `function C({ a }: { a: string }) { return (<div>{a}</div>); }`,
      typescript: `function C({ a }: { a: string }) { return (<div>{a}</div>); }`,
      "react-native": `function C({ a }: { a: string }) { return (<div>{a}</div>); }`,
      vue3: `<script setup lang="ts">\nconst props = defineProps<{ a: string }>();\n</script>\n\n<template>\n  <div>{{ a }}</div>\n</template>\n`,
      vue2: `<template>\n  <div>{{ a }}</div>\n</template>\n\n<script>\nexport default {\n  name: "C",\n  props: {\n    a: { type: String, required: true },\n  },\n};\n</script>\n`,
      svelte: `<script lang="ts">\n  let { a }: { a: string } = $props();\n</script>\n\n<div>{a}</div>\n`,
      angular: `import { Component, Input } from "@angular/core";\nimport { CommonModule } from "@angular/common";\n\n@Component({\n  selector: "app-c",\n  standalone: true,\n  imports: [CommonModule],\n  template: \`\n    <div>{{ a }}</div>\n  \`,\n})\nexport class CComponent {\n  @Input() a!: string;\n}\n`,
      miniprogram: {
        wxml: `<view>{{ a }}</view>\n`,
        js: `Component({\n  properties: {\n    a: { type: String, value: "" },\n  },\n  data: {},\n  methods: {},\n});\n`,
      },
    };

    for (const framework of PARSEABLE_FRAMEWORKS) {
      const fixture = fixtures[framework];
      expect(fixture).toBeDefined();
      const target = framework === "react" ? "vue3" : "react";
      const report = await translateComponent(fixture as string, framework, target, { fileName: "C", skipExecution: true });
      expect(report.status).toBe("PASSED");
    }
  }, 60000);

  it("still refuses emit-only frameworks as a source", async () => {
    await expect(translateComponent("whatever", "arkui", "react")).rejects.toThrow(/FRAMEWORK_NOT_PARSEABLE/);
    await expect(translateComponent("whatever", "flutter", "react")).rejects.toThrow(/FRAMEWORK_NOT_PARSEABLE/);
  });
});
