/**
 * Exercises every supported direction pair with the real toolchains.
 *
 * Six frameworks can act as a source (React, TypeScript, Vue 3, Vue 2,
 * Svelte, Angular, WeChat Mini Program) and ten can act as a target, so
 * this drives the full cross product rather than a representative sample.
 * Where both sides can really run, the SSR comparison runs too.
 */
import { translateComponent } from "../src/engine";
import { parseReactComponent } from "../src/parsers/react";
import { parseVue2Component } from "../src/parsers/vue2";
import { parseVue3Component } from "../src/parsers/vue3";
import { parseSvelteComponent } from "../src/parsers/svelte";
import { parseAngularComponent } from "../src/parsers/angular";
import { parseMiniProgramComponent } from "../src/parsers/miniprogram";
import { emitReact } from "../src/emitters/react";
import { emitVue3 } from "../src/emitters/vue3";
import { emitVue2 } from "../src/emitters/vue2";
import { emitSvelte } from "../src/emitters/svelte";
import { emitAngular } from "../src/emitters/angular";
import { emitMiniProgram } from "../src/emitters/miniprogram";
import { ComponentDef, DialectError, EXECUTABLE_FRAMEWORKS, Framework } from "../src/models";

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

const IR: ComponentDef = parseReactComponent(COUNTER, "Counter.tsx");

/** One real source document per parseable framework, produced by that
 * framework's own emitter so the fixtures cannot drift from the emitters. */
const SOURCES: Record<string, { source: string | { wxml: string; js: string }; fileName: string }> = {
  react: { source: emitReact(IR), fileName: "Counter.tsx" },
  vue3: { source: emitVue3(IR), fileName: "Counter.vue" },
  vue2: { source: emitVue2(IR), fileName: "Counter.vue" },
  svelte: { source: emitSvelte(IR), fileName: "Counter.svelte" },
  angular: { source: emitAngular(IR), fileName: "counter.component.ts" },
  miniprogram: { source: emitMiniProgram(IR), fileName: "Counter" },
};

const TARGETS: Framework[] = [
  "react", "typescript", "vue3", "vue2", "angular", "svelte",
  "react-native", "miniprogram", "arkui", "flutter",
];

const PAIRS: [string, Framework][] = Object.keys(SOURCES).flatMap(
  (from) => TARGETS.filter((to) => to !== from).map((to): [string, Framework] => [from, to]),
);

describe("every direction pair", () => {
  it.each(PAIRS)("%s -> %s translates and passes the target's real compiler", async (from, to) => {
    const fixture = SOURCES[from];
    if (!fixture) throw new Error(`no fixture for ${from}`);
    const report = await translateComponent(fixture.source as string, from, to, { fileName: fixture.fileName });

    expect(report.status).toBe("PASSED");
    expect(report.validation?.syntaxStatus).toBe("PASSED");
    expect(report.emitted ?? report.emittedFiles).toBeTruthy();

    // When both sides can really run, the behavioral comparison must have
    // actually happened -- not silently degraded to a skip.
    const bothRunnable = EXECUTABLE_FRAMEWORKS.has(from as Framework) && EXECUTABLE_FRAMEWORKS.has(to);
    expect(report.validation?.executionStatus).toBe(bothRunnable ? "PASSED" : "EXECUTION_NOT_AVAILABLE");
  }, 60000);

  it("covers 54 pairs", () => {
    expect(PAIRS).toHaveLength(54);
  });
});

describe("round trips through each real parser", () => {
  it("React -> Vue 3 -> canonical is exact", () => {
    expect(parseVue3Component(emitVue3(IR), "Counter.vue")).toEqual(IR);
  });

  it("React -> Svelte -> canonical is exact", () => {
    expect(parseSvelteComponent(emitSvelte(IR), "Counter.svelte")).toEqual(IR);
  });

  it("React -> Angular -> canonical is exact", () => {
    expect(parseAngularComponent(emitAngular(IR), "counter.component.ts")).toEqual(IR);
  });

  it("React -> Vue 2 -> canonical loses only the emit payload type", () => {
    const back = parseVue2Component(emitVue2(IR), "Counter.vue");
    expect(back.state).toEqual(IR.state);
    expect(back.root).toEqual(IR.root);
    expect(back.props).toEqual(IR.props.map((p) => (p.kind === "callback" ? { ...p, paramType: undefined } : p)));
  });

  it("React -> WeChat -> canonical loses only what WXML cannot express", () => {
    const back = parseMiniProgramComponent(emitMiniProgram(IR), "Counter");
    // The render tree and state survive intact -- that is the substance.
    expect(back.state).toEqual(IR.state);
    expect(back.root).toEqual(IR.root);
    // WeChat `properties` has no "required" concept and `triggerEvent`
    // carries an untyped detail, so those two facts cannot come back.
    expect(back.props).toEqual([
      { kind: "data", name: "label", propType: "string", required: false, defaultValue: { type: "string", value: "" } },
      { kind: "data", name: "step", propType: "number", required: false, defaultValue: { type: "number", value: 1 } },
      { kind: "callback", name: "onDone", paramType: undefined },
    ]);
  });
});

describe("documented information loss is reported, not hidden", () => {
  it("flags the Vue 2 payload-type loss", async () => {
    const report = await translateComponent(COUNTER, "react", "vue2", { fileName: "Counter.tsx", skipExecution: true });
    expect(report.notes.join(" ")).toMatch(/no typed emit declaration/);
  });

  it("flags both WeChat losses", async () => {
    const report = await translateComponent(COUNTER, "react", "miniprogram", { fileName: "Counter.tsx", skipExecution: true });
    expect(report.notes.join(" ")).toMatch(/cannot express a required prop/);
    expect(report.notes.join(" ")).toMatch(/untyped detail/);
  });
});

describe("new parsers fail closed", () => {
  const cases: [string, () => unknown][] = [
    ["Svelte with an unsupported rune", () => parseSvelteComponent(`<script lang="ts">\n  let x = $derived(1);\n</script>\n<div>{x}</div>`, "C.svelte")],
    ["Svelte with an each block", () => parseSvelteComponent(`<script lang="ts">\n</script>\n<div>{#each [1] as n}<span>{n}</span>{/each}</div>`, "C.svelte")],
    ["Svelte with two roots", () => parseSvelteComponent(`<script lang="ts">\n</script>\n<div>a</div><div>b</div>`, "C.svelte")],
    ["Angular with templateUrl", () => parseAngularComponent(`import { Component } from "@angular/core";\n@Component({ selector: "a", templateUrl: "./a.html" })\nexport class AComponent {}`, "a.component.ts")],
    ["Angular with a method", () => parseAngularComponent(`import { Component } from "@angular/core";\n@Component({ selector: "a", template: \`<div>x</div>\` })\nexport class AComponent { go() { return 1; } }`, "a.component.ts")],
    ["Angular with *ngFor", () => parseAngularComponent(`import { Component } from "@angular/core";\n@Component({ selector: "a", template: \`<div><span *ngFor="let i of items">{{ i }}</span></div>\` })\nexport class AComponent {}`, "a.component.ts")],
    ["WeChat with an unknown component", () => parseMiniProgramComponent({ wxml: `<scroll-view>x</scroll-view>`, js: `Component({ properties: {}, data: {}, methods: {} });` }, "C")],
    ["WeChat with a lifetime hook", () => parseMiniProgramComponent({ wxml: `<view>x</view>`, js: `Component({ properties: {}, data: {}, methods: {}, lifetimes: { attached() {} } });` }, "C")],
    ["WeChat with wx:elif", () => parseMiniProgramComponent({ wxml: `<view><text wx:if="{{ a }}">x</text><text wx:elif="{{ b }}">y</text></view>`, js: `Component({ properties: {}, data: { a: true, b: false }, methods: {} });` }, "C")],
  ];

  it.each(cases)("blocks %s", (_name, run) => {
    expect(run).toThrow(DialectError);
  });
});
