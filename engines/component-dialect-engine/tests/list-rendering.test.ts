/**
 * List rendering -- the first certified-component-v1 subset expansion.
 *
 * List rendering was the single most common blocker in real UI code (the
 * profile's own original negative-case list opened with `.map`), so it is
 * covered here at the same standard as the base profile: every target's
 * real compiler, exact round trips through every list-capable source, and
 * real SSR comparison with genuine sample rows.
 */
import { translateComponent } from "../src/engine";
import { parseReactComponent } from "../src/parsers/react";
import { parseVue3Component } from "../src/parsers/vue3";
import { parseSvelteComponent } from "../src/parsers/svelte";
import { parseAngularComponent } from "../src/parsers/angular";
import { parseVue2Component } from "../src/parsers/vue2";
import { parseMiniProgramComponent } from "../src/parsers/miniprogram";
import { emitReact } from "../src/emitters/react";
import { emitVue3 } from "../src/emitters/vue3";
import { emitVue2 } from "../src/emitters/vue2";
import { emitSvelte } from "../src/emitters/svelte";
import { emitAngular } from "../src/emitters/angular";
import { emitMiniProgram } from "../src/emitters/miniprogram";
import { emitFlutter } from "../src/emitters/flutter";
import { emitArkUI } from "../src/emitters/arkui";
import { compareRendered, defaultExecutionCases } from "../src/execution";
import { ComponentDef, DialectError, Framework } from "../src/models";

/** Exercises both element shapes at once: a primitive list (its own key)
 * and an object list (keyed by a declared field). */
const TAG_LIST = `
function TagList({ title, tags, rows }: { title: string; tags: string[]; rows: { id: number; label: string }[] }) {
  return (
    <div className="tags">
      <h2>{title}</h2>
      <ul>{tags.map((tag) => (<li>{tag}</li>))}</ul>
      <ul>{rows.map((row) => (<li className="row"><strong>{row.label}</strong></li>))}</ul>
    </div>
  );
}
`;

const IR: ComponentDef = parseReactComponent(TAG_LIST, "TagList.tsx");

const NESTED_OBJECT_LIST = `
function BehaviorRows({ behavior }: { behavior: { targets: { language: string; build_analysis: { total: number; status: string } }[] } }) {
  return <ul>{behavior.targets.map((target) => <li key={target.language}>{target.language}: {target.build_analysis.total} / {target.build_analysis.status}</li>)}</ul>;
}
`;

describe("list props are modelled, not flattened", () => {
  it("reads a primitive list and an object list with its key field", () => {
    expect(IR.props).toEqual([
      { kind: "data", name: "title", propType: "string", required: true, defaultValue: undefined },
      { kind: "list", name: "tags", element: { kind: "primitive", primitive: "string" }, keyField: undefined },
      { kind: "list", name: "rows", element: { kind: "object", fields: {
        id: { shape: { kind: "primitive", primitive: "number" }, optional: false },
        label: { shape: { kind: "primitive", primitive: "string" }, optional: false },
      } }, keyField: "id" },
    ]);
  });

  it("models the loop body as a list node with a bound item variable", () => {
    if (IR.root.kind !== "element") throw new Error("expected an element root");
    const lists = IR.root.children.flatMap((c) => (c.kind === "element" ? c.children : [])).filter((c) => c.kind === "list");
    expect(lists).toHaveLength(2);
  });

  it("accepts an explicit stable key when the field name is not conventional", () => {
    const ir = parseReactComponent(`
      function Events({ events }: { events: { eventId: string; label: string }[] }) {
        return (<ul>{events.map((event) => <li key={event.eventId}>{event.label}</li>)}</ul>);
      }
    `, "Events.tsx");
    const list = ir.root.kind === "element" ? ir.root.children[0] : undefined;
    expect(list?.kind).toBe("list");
    expect(ir.props.find((prop) => prop.kind === "list")?.keyField).toBe("eventId");
    expect(emitMiniProgram(ir)["wxml"]).toContain('wx:for="{{ events }}" wx:for-item="event" wx:key="eventId"');
  });

  it("retains a bounded nested object path across emitters", () => {
    const ir = parseReactComponent(NESTED_OBJECT_LIST, "BehaviorRows.tsx");
    const list = ir.lists?.find((prop) => prop.name === "behavior.targets");
    expect(list?.kind).toBe("list");
    if (list?.kind !== "list" || list.element.kind !== "object") throw new Error("expected nested object list");
    const buildAnalysis = list.element.fields.build_analysis;
    expect(buildAnalysis).toBeDefined();
    expect(buildAnalysis?.shape).toEqual({
      kind: "object",
      fields: {
        total: { shape: { kind: "primitive", primitive: "number" }, optional: false },
        status: { shape: { kind: "primitive", primitive: "string" }, optional: false },
      },
    });
    expect(emitReact(ir)).toContain("target.build_analysis.total");
    expect(emitFlutter(ir)).toContain('target["build_analysis"]["total"]');
    expect(emitArkUI(ir)).toContain('target["build_analysis"]["total"]');
  });
});

describe("every target renders lists in its own idiom", () => {
  const TARGETS: Framework[] = [
    "typescript", "vue3", "vue2", "angular", "svelte",
    "react-native", "miniprogram", "arkui", "flutter",
  ];

  it.each(TARGETS)("react -> %s passes the target's real compiler", async (target) => {
    const report = await translateComponent(emitReact(IR), "react", target, { fileName: "TagList.tsx", skipExecution: true });
    expect(report.status).toBe("PASSED");
    expect(report.validation?.syntaxStatus).toBe("PASSED");
  }, 60000);

  it("uses each framework's own loop construct rather than a shared one", () => {
    expect(emitVue3(IR)).toContain('v-for="tag in tags" :key="tag"');
    expect(emitVue3(IR)).toContain('v-for="row in rows" :key="row.id"');
    expect(emitVue2(IR)).toContain('v-for="row in rows" :key="row.id"');
    expect(emitSvelte(IR)).toContain("{#each rows as row (row.id)}");
    expect(emitAngular(IR)).toContain('*ngFor="let row of rows"');
    expect(emitReact(IR)).toContain("rows.map((row) => (");
    expect(emitReact(IR)).toContain("key={row.id}");
  });

  it("uses WeChat's field-name key form, not an expression", () => {
    const wxml = emitMiniProgram(IR)["wxml"] as string;
    // `wx:key` takes a FIELD NAME for object items and the `*this` sentinel
    // for primitives. An expression there silently disables list diffing.
    expect(wxml).toContain('wx:for="{{ rows }}" wx:for-item="row" wx:key="id"');
    expect(wxml).toContain('wx:for="{{ tags }}" wx:for-item="tag" wx:key="*this"');
    expect(wxml).not.toContain('wx:key="row.id"');
  });
});

describe("round trips through every list-capable source", () => {
  it("React -> Vue 3 -> canonical is exact", () => {
    expect(parseVue3Component(emitVue3(IR), "TagList.vue")).toEqual(IR);
  });

  it("React -> Svelte -> canonical is exact", () => {
    expect(parseSvelteComponent(emitSvelte(IR), "TagList.svelte")).toEqual(IR);
  });

  it("React -> Angular -> canonical is exact", () => {
    expect(parseAngularComponent(emitAngular(IR), "tag-list.component.ts")).toEqual(IR);
  });
});

describe("real SSR comparison with genuine sample rows", () => {
  it("generates real rows rather than rendering empty lists", () => {
    const [first, second] = defaultExecutionCases(IR);
    // An empty sample would "prove" two frameworks agree on rendering
    // nothing -- the emptiest possible false pass.
    expect(first?.props["tags"]).toEqual(["item-1", "item-2"]);
    expect(first?.props["rows"]).toEqual([{ id: 1, label: "item-1" }, { id: 2, label: "item-2" }]);
    // A different row count catches an emitter that hard-codes an arity.
    expect((second?.props["rows"] as unknown[]).length).toBe(3);
  });

  it.each(["vue3", "svelte"] as const)("react and %s render identical DOM for both list shapes", async (target) => {
    const emit = { vue3: emitVue3, vue2: emitVue2, svelte: emitSvelte }[target];
    const result = await compareRendered(
      { framework: "react", source: emitReact(IR) },
      { framework: target, source: emit(IR) },
      defaultExecutionCases(IR),
    );
    expect(result).toEqual({ status: "PASSED", diagnostics: [] });
  }, 60000);

  it("does not claim local Vue 2 runtime evidence", async () => {
    const result = await compareRendered(
      { framework: "react", source: emitReact(IR) },
      { framework: "vue2", source: emitVue2(IR) },
      defaultExecutionCases(IR),
    );
    expect(result.status).toBe("FAILED");
    expect(result.diagnostics[0]).toMatch(/vue2 render threw: EXECUTION_NOT_AVAILABLE/);
  }, 60000);
});

describe("list rendering fails closed outside the certified shape", () => {
  const cases: [string, string][] = [
    ["an index parameter (position as identity)", `function C({ rows }: { rows: { id: number }[] }) { return (<ul>{rows.map((row, i) => (<li>{row.id}</li>))}</ul>); }`],
    ["a destructured item", `function C({ rows }: { rows: { id: number }[] }) { return (<ul>{rows.map(({ id }) => (<li>{id}</li>))}</ul>); }`],
    ["a block-bodied callback", `function C({ rows }: { rows: { id: number }[] }) { return (<ul>{rows.map((row) => { return (<li>{row.id}</li>); })}</ul>); }`],
    ["mapping over a non-prop expression", `function C({ rows }: { rows: { id: number }[] }) { return (<ul>{rows.slice(0).map((row) => (<li>{row.id}</li>))}</ul>); }`],
    ["object elements with no identity field", `function C({ rows }: { rows: { label: string; note: string }[] }) { return (<ul>{rows.map((row) => (<li>{row.label}</li>))}</ul>); }`],
    ["a field not declared on the element", `function C({ rows }: { rows: { id: number; label: string }[] }) { return (<ul>{rows.map((row) => (<li>{row.missing}</li>))}</ul>); }`],
    ["rendering an array field as scalar text", `function C({ rows }: { rows: { id: number; inner: number[] }[] }) { return (<ul>{rows.map((row) => (<li>{row.inner}</li>))}</ul>); }`],
    ["reading an object item without a field", `function C({ rows }: { rows: { id: number }[] }) { return (<ul>{rows.map((row) => (<li>{row}</li>))}</ul>); }`],
    ["interpolating a list prop directly", `function C({ rows }: { rows: { id: number }[] }) { return (<div>{rows}</div>); }`],
    ["a nested list", `function C({ a, b }: { a: { id: number }[]; b: { id: number }[] }) { return (<ul>{a.map((x) => (<li>{b.map((y) => (<span>{y.id}</span>))}</li>))}</ul>); }`],
  ];

  it.each(cases)("blocks %s", (_name, source) => {
    expect(() => parseReactComponent(source, "C.tsx")).toThrow(DialectError);
  });
});

describe("frameworks that cannot describe a list element say so", () => {
  // Vue 2's `type: Array` and WeChat's `{ type: Array, value: [] }` record
  // no element shape. Recovering it from template usage would be guessing at
  // field TYPES, so both fail closed as list SOURCES while staying valid
  // list targets.
  it("Vue 2 emits lists but refuses to parse them back", async () => {
    const emitted = emitVue2(IR);
    expect(emitted).toContain('v-for="row in rows"');
    expect(() => parseVue2Component(emitted, "TagList.vue")).toThrow(/UNRECOVERABLE_LIST_ELEMENT/);
  });

  it("WeChat emits lists but refuses to parse them back", () => {
    const bundle = emitMiniProgram(IR);
    expect(bundle["wxml"]).toContain("wx:for=");
    expect(() => parseMiniProgramComponent(bundle, "TagList")).toThrow(/UNRECOVERABLE_LIST_ELEMENT/);
  });

  it("reports that as a BLOCKED translation, not a crash", async () => {
    const report = await translateComponent(emitVue2(IR), "vue2", "react", { fileName: "TagList.vue", skipExecution: true });
    expect(report.status).toBe("BLOCKED");
    expect(report.reasonCode).toBe("CERTIFIED_COMPONENT_UNRECOVERABLE_LIST_ELEMENT");
  }, 60000);
});
