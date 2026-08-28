/**
 * Real, executed tests for certified-component-v1.
 *
 * These are not shape assertions over hand-written fixtures: every test
 * drives the actual framework toolchains -- the TypeScript Compiler API,
 * @vue/compiler-sfc, @wxml/parser -- and the SSR tests really render both
 * components with react-dom/server and @vue/server-renderer and compare
 * the resulting DOM.
 */
import { parseReactComponent, parseReactComponentResults } from "../src/parsers/react";
import { parseVue3Component } from "../src/parsers/vue3";
import { emitReact } from "../src/emitters/react";
import { emitVue3 } from "../src/emitters/vue3";
import { emitVue2 } from "../src/emitters/vue2";
import { emitMiniProgram } from "../src/emitters/miniprogram";
import { validateSyntax } from "../src/validator";
import { compareRendered, defaultExecutionCases, normalizeHtml } from "../src/execution";
import { DialectError } from "../src/models";

const COUNTER_TSX = `
function Counter({ label, step = 1, onDone }: { label: string; step?: number; onDone: (value: number) => void }) {
  const [count, setCount] = useState<number>(0);
  const [busy, setBusy] = useState<boolean>(false);
  return (
    <div className="counter">
      <span>{label}</span>
      <em>{count}</em>
      {step > 3 ? (<strong>big</strong>) : (<strong>small</strong>)}
      <button type="button" disabled={busy} onClick={() => { setCount(count + step); onDone(count); }}>add</button>
    </div>
  );
}
`;

describe("React parsing (real TypeScript Compiler API)", () => {
  it("extracts props, defaults, callbacks, state and the render tree", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    expect(ir.name).toBe("Counter");
    expect(ir.props).toEqual([
      { kind: "data", name: "label", propType: "string", required: true, defaultValue: undefined },
      { kind: "data", name: "step", propType: "number", required: false, defaultValue: { type: "number", value: 1 } },
      { kind: "callback", name: "onDone", paramType: "number" },
    ]);
    expect(ir.state.map((s) => s.name)).toEqual(["count", "busy"]);
    expect(ir.root.kind).toBe("element");
  });

  it("binds nonstandard useState setter names to the canonical state target", () => {
    const ir = parseReactComponent(`
      function Draft({ initial }: { initial: string }) {
        const [draft, updateDraft] = useState<string>("");
        return <input value={draft} onChange={(event) => updateDraft(event.target.value)} />;
      }
    `, "Draft.tsx");
    expect(ir.root).toMatchObject({
      kind: "element",
      events: [{ name: "onChange", body: [{ kind: "setState", target: "draft", value: { kind: "eventValue" } }] }],
    });
    expect(emitReact(ir)).toContain("setDraft(event.target.value)");
  });

  it("erases only pure synchronous useMemo wrappers", () => {
    const ir = parseReactComponent(`
      function Memo({ value }: { value: number }) {
        const doubled = useMemo(() => Math.max(0, value * 2), [value]);
        return <span>{doubled}</span>;
      }
    `, "Memo.tsx");
    expect(ir.root).toMatchObject({
      kind: "element",
      children: [{ kind: "text", value: { kind: "numericFunction", function: "max" } }],
    });
    expect(() => parseReactComponent(`
      function UnsafeMemo({ value }: { value: number }) {
        const result = useMemo(() => fetch(String(value)), [value]);
        return <span>{result}</span>;
      }
    `, "UnsafeMemo.tsx")).toThrow(DialectError);
  });

  it("folds the fixed epoch ISO fallback inside a closed state object", () => {
    const ir = parseReactComponent(`
      function EpochState() {
        const [snapshot, replaceSnapshot] = useState<{ fetchedAt: string }>({ fetchedAt: new Date(0).toISOString() });
        return <span>{snapshot.fetchedAt}</span>;
      }
    `, "EpochState.tsx");
    expect(ir.state[0]?.initial).toMatchObject({
      kind: "objectLiteral",
      fields: [{ name: "fetchedAt", value: { kind: "literal", literal: { type: "string", value: "1970-01-01T00:00:00.000Z" } } }],
    });
  });

  it("inlines earlier pure local expressions without widening the target IR", () => {
    const ir = parseReactComponent(`
      function Alias({ name }: { name: string }) {
        const heading = name;
        const display = true ? heading : "unused";
        return (<p>{display}</p>);
      }
    `, "Alias.tsx");
    expect(ir.root.kind).toBe("element");
    const child = ir.root.kind === "element" ? ir.root.children[0] : undefined;
    expect(child).toEqual({
      kind: "text",
      value: {
        kind: "ternary",
        condition: { kind: "literal", literal: { type: "boolean", value: true } },
        then: { kind: "ident", name: "name" },
        else: { kind: "literal", literal: { type: "string", value: "unused" } },
      },
    });
  });

  it("preserves certified string methods and static label-map lookups", () => {
    const ir = parseReactComponent(`
      const labels = { READY: "就绪", BLOCKED: "阻断" };
      function Label({ status }: { status: string }) {
        const normalized = status.toUpperCase();
        return <span aria-hidden={true}>{labels[normalized] ?? status}</span>;
      }
    `, "Label.tsx");
    expect(ir.root).toEqual({
      kind: "element",
      tag: "span",
      attrs: [{ kind: "dynamic", name: "aria-hidden", value: { kind: "literal", literal: { type: "boolean", value: true } } }],
      events: [],
      children: [{
        kind: "text",
        value: {
          kind: "binary",
          operator: "??",
          left: {
            kind: "ternary",
            condition: { kind: "binary", operator: "==", left: { kind: "stringMethod", method: "toUpperCase", receiver: { kind: "ident", name: "status" }, args: [] }, right: { kind: "literal", literal: { type: "string", value: "READY" } } },
            then: { kind: "literal", literal: { type: "string", value: "就绪" } },
            else: {
              kind: "ternary",
              condition: { kind: "binary", operator: "==", left: { kind: "stringMethod", method: "toUpperCase", receiver: { kind: "ident", name: "status" }, args: [] }, right: { kind: "literal", literal: { type: "string", value: "BLOCKED" } } },
              then: { kind: "literal", literal: { type: "string", value: "阻断" } },
              else: { kind: "literal", literal: { type: "null" } },
            },
          },
          right: { kind: "ident", name: "status" },
        },
      }],
    });
    expect(emitReact(ir)).toContain("status.toUpperCase()");
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("retains typed nested object paths and array length reads", () => {
    const ir = parseReactComponent(`
      function Summary({ report }: { report: { totals: { count: number }; items: string[] } }) {
        return <p>{report.totals.count} / {report.items.length}</p>;
      }
    `, "Summary.tsx");
    expect(ir.root.kind).toBe("element");
    const values = ir.root.kind === "element" ? ir.root.children.filter((child) => child.kind === "text").map((child) => child.value) : [];
    expect(values).toEqual([
      { kind: "path", object: "report", fields: ["totals", "count"] },
      { kind: "literal", literal: { type: "string", value: "/" } },
      { kind: "arrayLength", operand: { kind: "member", object: "report", field: "items" } },
    ]);
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("retains bounded regex validation, includes, and input event values", () => {
    const ir = parseReactComponent(`
      const projectRefPattern = /^[a-z0-9][a-z0-9._/-]{2,180}$/i;
      function SmokeInput() {
        const [draft, setDraft] = useState<string>("");
        const valid = projectRefPattern.test(draft.trim()) && !draft.includes("..");
        return <div>
          <input value={draft} maxLength={180} onChange={(event) => setDraft(event.target.value)} />
          <button disabled={!valid} onClick={() => setDraft(draft.trim())}>load</button>
        </div>;
      }
    `, "SmokeInput.tsx");
    expect(ir.root).toMatchObject({ kind: "element" });
    const input = ir.root.kind === "element" ? ir.root.children[0] : undefined;
    expect(input).toMatchObject({
      kind: "element",
      tag: "input",
      attrs: [
        { kind: "dynamic", name: "value", value: { kind: "ident", name: "draft" } },
        { kind: "dynamic", name: "maxLength", value: { kind: "literal", literal: { type: "number", value: 180 } } },
      ],
      events: [{ name: "onChange", body: [{ kind: "setState", target: "draft", value: { kind: "eventValue" } }] }],
    });
    const button = ir.root.kind === "element" ? ir.root.children[1] : undefined;
    expect(button).toMatchObject({
      kind: "element",
      events: [{ name: "onClick" }],
    });
    expect(emitReact(ir)).toContain("/^[a-z0-9][a-z0-9._/-]{2,180}$/i.test(draft.trim())");
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("accepts only static Math bounds and CSS Module class tokens", () => {
    const ir = parseReactComponent(`
      import styles from "./Empty.module.css";
      function Empty({ count }: { count: number }) {
        return <div className={styles.empty}>{Math.min(100, Math.max(0, count))}</div>;
      }
    `, "Empty.tsx");
    expect(ir.root).toMatchObject({
      kind: "element",
      attrs: [{ kind: "dynamic", name: "class", value: { kind: "cssModuleClass", className: "empty" } }],
      children: [{
        kind: "text",
        value: {
          kind: "numericFunction",
          function: "min",
          args: [{ kind: "literal", literal: { type: "number", value: 100 } }, {
            kind: "numericFunction",
            function: "max",
          }],
        },
      }],
    });
    expect(emitReact(ir)).toContain('className={"empty"}');
    expect(emitReact(ir)).toContain("Math.min(100, Math.max(0, count))");
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("keeps bounded numeric and string helpers typed across targets", () => {
    const ir = parseReactComponent(`
      function Helpers({ value, label }: { value: number; label: string }) {
        return <p>{Math.floor(value)} / {Math.ceil(value)} / {Math.abs(value)} / {label.startsWith("A") ? label.slice(0, 2) : label.endsWith("!") ? label.slice(1) : label}</p>;
      }
    `, "Helpers.tsx");
    expect(ir.root).toMatchObject({
      kind: "element",
      children: [
        { kind: "text", value: { kind: "numericFunction", function: "floor" } },
        { kind: "text", value: { kind: "literal", literal: { type: "string", value: "/" } } },
        { kind: "text", value: { kind: "numericFunction", function: "ceil" } },
        { kind: "text", value: { kind: "literal", literal: { type: "string", value: "/" } } },
        { kind: "text", value: { kind: "numericFunction", function: "abs" } },
        { kind: "text", value: { kind: "literal", literal: { type: "string", value: "/" } } },
        { kind: "text", value: { kind: "ternary" } },
      ],
    });
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("keeps bounded number formatting and percentage width in the shared IR", () => {
    const ir = parseReactComponent(`
      import { formatQuota } from "../lib/pricingCatalog";
      function UsageMeter({ label, measure }: { label: string; measure: { consumed: number; usageBps: number } }) {
        const visualPercent = Math.min(100, measure.usageBps / 100);
        return <article>
          <strong>{formatQuota(measure.consumed)}</strong>
          <em>{(measure.usageBps / 100).toFixed(2)}</em>
          <span style={{ width: \`\${visualPercent}%\` }}>{label}</span>
        </article>;
      }
    `, "UsageMeter.tsx");
    expect(ir.root).toMatchObject({
      kind: "element",
      children: [
        { kind: "element", tag: "strong", children: [{ kind: "text", value: { kind: "numberFormat", format: "grouped" } }] },
        { kind: "element", tag: "em", children: [{ kind: "text", value: { kind: "numberMethod", method: "toFixed", fractionDigits: 2 } }] },
        { kind: "element", tag: "span", attrs: [{ kind: "dynamic", name: "style", value: { kind: "styleObject" } }] },
      ],
    });
    expect(emitReact(ir)).toContain('toLocaleString("zh-CN")');
    expect(emitReact(ir)).toContain('style={{ width: Math.min(100, measure.usageBps / 100) + "%" }}');
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("preserves an explicit en-US number-format locale", () => {
    const ir = parseReactComponent(`
      function Count({ value }: { value: number }) {
        return <strong>{value.toLocaleString("en-US")}</strong>;
      }
    `, "Count.tsx");
    expect(ir.root).toMatchObject({
      kind: "element",
      children: [{ kind: "text", value: { kind: "numberFormat", format: "grouped", locale: "en-US" } }],
    });
    expect(emitReact(ir)).toContain('value.toLocaleString("en-US")');
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue2", emitVue2(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("lowers only the exact Next Link import to a cross-target anchor", () => {
    const ir = parseReactComponent(`
      import Link from "next/link";
      function Landing() {
        return <div><Link className="button" href="/pricing">查看套餐</Link></div>;
      }
    `, "Landing.tsx");
    expect(ir.root).toMatchObject({
      kind: "element",
      children: [{ kind: "element", tag: "a", attrs: [
        { kind: "static", name: "class", value: "button" },
        { kind: "static", name: "href", value: "/pricing" },
      ] }],
    });
    expect(emitReact(ir)).toContain('<a className="button" href="/pricing">');
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("materializes immutable object and tuple collections without dropping list identity", () => {
    const ir = parseReactComponent(`
      const cards = [
        { id: "spring", title: "Spring", href: "/spring" },
        { id: "routes", title: "Routes", href: "/translation" },
      ] as const;
      const notices = [
        ["证据", "NOT_RUN"],
        ["认证", "BLOCKED"],
      ] as const;
      function StaticCollections() {
        return <section>
          <div>{cards.map((card) => <a href={card.href} key={card.id}>{card.title}</a>)}</div>
          <div>{notices.map(([title, status]) => <p key={title}>{title}: {status}</p>)}</div>
        </section>;
      }
    `, "StaticCollections.tsx");
    expect(ir.lists).toHaveLength(2);
    expect(ir.lists?.map((list) => [list.name, list.keyField, list.staticItems?.length])).toEqual([
      ["cards", "id", 2],
      ["notices", "item0", 2],
    ]);
    expect(emitReact(ir)).toContain("const cards = [{ id: \"spring\"");
    expect(emitReact(ir)).toContain("const notices = [{ item0: \"证据\"");
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("preserves a typed lookup across immutable object-of-array collections", () => {
    const ir = parseReactComponent(`
      const groups = {
        first: [{ id: "a", label: "A" }],
        second: [{ id: "b", label: "B" }],
      } as const;
      function Groups({ selected }: { selected: string }) {
        const items = groups[selected];
        return <ul>{items.map((item) => <li key={item.id}>{item.label}</li>)}</ul>;
      }
    `, "Groups.tsx");
    expect(ir.lists?.find((list) => list.name === "items")).toMatchObject({
      element: { kind: "object", fields: { id: { shape: { kind: "primitive", primitive: "string" } } } },
      keyField: "id",
      sourceExpression: { kind: "objectLookup", object: { kind: "objectLiteral" }, key: { kind: "ident", name: "selected" } },
    });
    expect(emitReact(ir)).toContain('({ first: [{ id: "a", label: "A" }], second: [{ id: "b", label: "B" }] })[selected]');
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue2", emitVue2(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("resolves closed object state aliases without widening the state shape", () => {
    const ir = parseReactComponent(`
      const initial = { enabled: false, count: 0, note: null } as const;
      function StateAlias() {
        const [state, setState] = useState<{ enabled: boolean; count: number; note: string | null }>(initial);
        return <span>{state.enabled ? state.count : 0}</span>;
      }
    `, "StateAlias.tsx");
    expect(ir.state).toEqual([{
      name: "state",
      stateType: "string",
      stateShape: {
        kind: "object",
        fields: {
          enabled: { shape: { kind: "primitive", primitive: "boolean" }, optional: false },
          count: { shape: { kind: "primitive", primitive: "number" }, optional: false },
          note: { shape: { kind: "primitive", primitive: "string", nullable: true }, optional: false },
        },
      },
      initial: {
        kind: "objectLiteral",
        fields: [
          { name: "enabled", value: { kind: "literal", literal: { type: "boolean", value: false } } },
          { name: "count", value: { kind: "literal", literal: { type: "number", value: 0 } } },
          { name: "note", value: { kind: "literal", literal: { type: "null" } } },
        ],
      },
    }]);
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("resolves local literal-union aliases, indexed access and ReadonlyArray state without any", () => {
    const ir = parseReactComponent(`
      type SessionState = {
        status: "loading" | "ready" | "blocked";
        rows: ReadonlyArray<{ id: string; label: string }>;
      };
      function SessionBadge() {
        const [status, setStatus] = useState<SessionState["status"]>("loading");
        const [rows, setRows] = useState<SessionState["rows"]>([]);
        return <div><span>{status}</span><ul>{rows.map((row) => <li key={row.id}>{row.label}</li>)}</ul></div>;
      }
    `, "SessionBadge.tsx");
    expect(ir.state.find((state) => state.name === "status")).toMatchObject({ stateType: "string", initial: { type: "string", value: "loading" } });
    expect(ir.state.find((state) => state.name === "rows")?.stateShape).toMatchObject({ kind: "array", element: { kind: "object" } });
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("keeps incompatible union object layouts blocked instead of accepting the first member", () => {
    const result = parseReactComponentResults(`
      function UnsafeUnion() {
        const [value, setValue] = useState<{ left: string } | { right: number }>({ left: "x" });
        return <span>blocked</span>;
      }
    `, "UnsafeUnion.tsx")[0];
    expect(result?.component).toBeNull();
    expect(result?.error?.code).toBe("CERTIFIED_COMPONENT_UNSUPPORTED_TYPE");
    expect(result?.error?.reason).toMatch(/incompatible union member shapes/);
  });

  it("keeps typed map/filter projections in the shared collection IR", () => {
    const ir = parseReactComponent(`
      const statuses = ["PASSED", "BLOCKED"] as const;
      function Derived({ counts }: { counts: { PASSED: number; BLOCKED: number } }) {
        const segments = statuses
          .map((status) => ({ status, count: counts[status] }))
          .filter((segment) => segment.count > 0);
        return <div>{segments.map((segment) => <span key={segment.status}>{segment.status}</span>)}</div>;
      }
    `, "Derived.tsx");
    expect(ir.lists?.find((list) => list.name === "segments")).toMatchObject({
      element: { kind: "object" },
      keyField: "status",
      sourceExpression: { kind: "collectionFilter", source: { kind: "collectionMap" } },
    });
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("inlines same-file pure primitive helpers and preserves finite checks", () => {
    const result = parseReactComponentResults(`
      function finiteCount(value: number): number {
        return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
      }
      function Bounded({ value }: { value: number }) {
        return <p>{finiteCount(value)}</p>;
      }
    `, "Bounded.tsx").find((candidate) => candidate.name === "Bounded");
    expect(result?.error).toBeNull();
    const ir = result?.component;
    expect(ir).not.toBeNull();
    if (ir === null || ir === undefined) throw new Error("BOUNDED_COMPONENT_NOT_PARSED");
    const value = ir.root.kind === "element" ? ir.root.children[0] : undefined;
    expect(value).toEqual({
      kind: "text",
      value: {
        kind: "ternary",
        condition: {
          kind: "binary",
          operator: "&&",
          left: { kind: "numericPredicate", predicate: "isFinite", operand: { kind: "ident", name: "value" } },
          right: { kind: "binary", operator: ">", left: { kind: "ident", name: "value" }, right: { kind: "literal", literal: { type: "number", value: 0 } } },
        },
        then: { kind: "numericFunction", function: "floor", args: [{ kind: "ident", name: "value" }] },
        else: { kind: "literal", literal: { type: "number", value: 0 } },
      },
    });
    expect(emitReact(ir)).toContain("Number.isFinite(value)");
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("preserves transparent JSX fragments across the canonical tree and template targets", () => {
    const ir = parseReactComponent(`
      function Fragmented({ ready }: { ready: boolean }) {
        return <section>{ready ? (
          <>
            <strong>ready</strong>
            <span>details</span>
          </>
        ) : <em>waiting</em>}</section>;
      }
    `, "Fragmented.tsx");
    expect(ir.root).toMatchObject({
      kind: "element",
      children: [{
        kind: "conditional",
        then: {
          kind: "fragment",
          children: [
            { kind: "element", tag: "strong" },
            { kind: "element", tag: "span" },
          ],
        },
        else: { kind: "element", tag: "em" },
      }],
    });
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("normalizes a bounded early JSX return into a target-neutral conditional", () => {
    const ir = parseReactComponent(`
      function Guard({ ready }: { ready: boolean }) {
        if (ready) {
          return <strong>ready</strong>;
        }
        return <em>waiting</em>;
      }
    `, "Guard.tsx");
    expect(ir.root).toEqual({
      kind: "conditional",
      condition: { kind: "ident", name: "ready" },
      then: { kind: "element", tag: "strong", attrs: [], events: [], children: [{ kind: "text", value: { kind: "literal", literal: { type: "string", value: "ready" } } }] },
      else: { kind: "element", tag: "em", attrs: [], events: [], children: [{ kind: "text", value: { kind: "literal", literal: { type: "string", value: "waiting" } } }] },
    });
    expect(validateSyntax("react", emitReact(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("vue3", emitVue3(ir))).toEqual({ status: "PASSED", diagnostics: [] });
    expect(validateSyntax("miniprogram", emitMiniProgram(ir))).toEqual({ status: "PASSED", diagnostics: [] });
  });
});

describe("cross-framework round trip", () => {
  it("React -> Vue 3 -> React produces an identical canonical model", () => {
    const first = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const vue = emitVue3(first);
    const second = parseVue3Component(vue, "Counter.vue");
    expect(second).toEqual(first);
  });

  it("re-emitted React is accepted by the real TypeScript parser", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const report = validateSyntax("react", emitReact(ir));
    expect(report).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("emitted Vue 3 is accepted by the real @vue/compiler-sfc", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const report = validateSyntax("vue3", emitVue3(ir));
    expect(report).toEqual({ status: "PASSED", diagnostics: [] });
  });

  it("emitted WeChat mini program bundle is accepted by the real @wxml/parser", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const report = validateSyntax("miniprogram", emitMiniProgram(ir));
    expect(report).toEqual({ status: "PASSED", diagnostics: [] });
  });
});

describe("real SSR execution comparison", () => {
  it("React and Vue 3 render identical DOM for the same props", async () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const result = await compareRendered(
      { framework: "react", source: emitReact(ir) },
      { framework: "vue3", source: emitVue3(ir) },
      defaultExecutionCases(ir),
    );
    expect(result).toEqual({ status: "PASSED", diagnostics: [] });
  }, 30000);

  it("detects a real behavioral divergence rather than rubber-stamping it", async () => {
    // A deliberately wrong "translation": the Vue side renders a different
    // element than the React side. If the execution leg were cosmetic this
    // would pass; it must fail.
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const brokenVue = emitVue3(ir).replace("<em>", "<span>").replace("</em>", "</span>");
    const result = await compareRendered(
      { framework: "react", source: emitReact(ir) },
      { framework: "vue3", source: brokenVue },
      defaultExecutionCases(ir),
    );
    expect(result.status).toBe("FAILED");
    expect(result.diagnostics.length).toBeGreaterThan(0);
  }, 30000);
});

describe("WeChat mini program semantics", () => {
  it("maps HTML tags to mini program built-in components", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const bundle = emitMiniProgram(ir);
    expect(bundle["wxml"]).toContain("<view class=\"counter\">");
    expect(bundle["wxml"]).not.toContain("<div");
    expect(bundle["wxml"]).toContain("bindtap=");
    expect(bundle["wxml"]).toContain("wx:if=");
  });

  it("writes state only through setData, never by assignment", () => {
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const js = emitMiniProgram(ir)["js"] as string;
    expect(js).toContain("this.setData({");
    expect(js).not.toMatch(/this\.data\.\w+\s*=/);
  });

  it("preserves React closure semantics across the synchronous setData boundary", () => {
    // In React, `setCount(count + step); onDone(count)` passes the OLD count.
    // WeChat's setData updates this.data synchronously, so a naive
    // transliteration would pass the NEW count. The emitter must snapshot.
    const ir = parseReactComponent(COUNTER_TSX, "Counter.tsx");
    const js = emitMiniProgram(ir)["js"] as string;
    expect(js).toContain("const count$0 = this.data.count;");
    expect(js).toContain("this.triggerEvent(\"done\", { value: count$0 });");
  });
});

describe("fail-closed behavior outside certified-component-v1", () => {
  const cases: [string, string][] = [
    ["array state", `function C() { const [x, setX] = useState<number[]>([]); return (<div>{x}</div>); }`],
    ["unsupported hook", `function C() { useEffect(() => {}, []); return (<div>hi</div>); }`],
    ["unsupported tag", `function C() { return (<video>hi</video>); }`],
    ["unsupported attribute", `function C() { return (<div data-tracking="x">hi</div>); }`],
    ["spread props", `function C(props: { a: string }) { return (<div {...props}>hi</div>); }`],
    ["unsupported method call in expression", `function C({ a }: { a: string }) { return (<div>{a.charAt(0)}</div>); }`],
    ["two components in one file", `function A() { return (<div>a</div>); } function B() { return (<div>b</div>); }`],
    ["untyped props", `function C(props) { return (<div>hi</div>); }`],
    ["handler with a loop", `function C() { const [x, setX] = useState<number>(0); return (<button onClick={() => { for (;;) {} }}>go</button>); }`],
    ["non-literal useState", `function C({ a }: { a: number }) { const [x, setX] = useState<number>(a); return (<div>{x}</div>); }`],
    ["forward local read", `function C({ a }: { a: number }) { const b = a + c; const c = a + 1; return (<div>{b}</div>); }`],
    ["cyclic local read", `function C({ a }: { a: number }) { const b = c; const c = b; return (<div>{b}</div>); }`],
  ];

  it.each(cases)("blocks %s instead of guessing", (_name, source) => {
    expect(() => parseReactComponent(source, "C.tsx")).toThrow(DialectError);
  });

  it("blocks a Vue SFC that uses the Options API rather than <script setup>", () => {
    const sfc = `<script>export default { data() { return { x: 1 }; } }</script>\n<template><div>{{ x }}</div></template>`;
    expect(() => parseVue3Component(sfc, "C.vue")).toThrow(DialectError);
  });

  it("blocks a Vue template with multiple root elements", () => {
    const sfc = `<script setup lang="ts">\n</script>\n<template><div>a</div><div>b</div></template>`;
    expect(() => parseVue3Component(sfc, "C.vue")).toThrow(DialectError);
  });

  it("carries a machine-readable reason code on every block", () => {
    try {
      parseReactComponent(`function C() { return (<video>hi</video>); }`, "C.tsx");
      throw new Error("expected a DialectError");
    } catch (error) {
      expect(error).toBeInstanceOf(DialectError);
      expect((error as DialectError).code).toBe("CERTIFIED_COMPONENT_UNSUPPORTED_TAG");
    }
  });
});

describe("html normalization used by the execution leg", () => {
  it("ignores comment markers and attribute order but not content", () => {
    expect(normalizeHtml(`<!--[--><div b="2" a="1">x</div><!--]-->`)).toBe(normalizeHtml(`<div a="1" b="2">x</div>`));
    expect(normalizeHtml(`<div>x</div>`)).not.toBe(normalizeHtml(`<div>y</div>`));
    expect(normalizeHtml(`<div a="1">x</div>`)).not.toBe(normalizeHtml(`<div a="2">x</div>`));
  });
});
