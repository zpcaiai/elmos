/**
 * Component composition and multi-component files.
 *
 * Both expansions came from a coverage scan of real application code, not
 * from intuition. The scan showed that `CERTIFIED_COMPONENT_UNSUPPORTED_TAG`
 * was mostly NOT about HTML tags -- 8 of 9 were component references like
 * `<TranslationStudio />` -- and that 11 of 28 files were blocked purely
 * because they declared more than one component.
 *
 * The interesting risk here is per-target registration. On four of the ten
 * targets a child reference compiles perfectly and then renders NOTHING
 * unless a second, separate registration step is also emitted.
 */
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { translateComponent } from "../src/engine";
import { runRepository } from "../src/pipeline";
import { parseReactComponent, parseReactComponents, parseReactComponentResults } from "../src/parsers/react";
import { emitReact, referencedComponents } from "../src/emitters/react";
import { emitVue3 } from "../src/emitters/vue3";
import { emitVue2 } from "../src/emitters/vue2";
import { emitSvelte } from "../src/emitters/svelte";
import { emitAngular } from "../src/emitters/angular";
import { emitMiniProgram } from "../src/emitters/miniprogram";
import { emitArkUI } from "../src/emitters/arkui";
import { emitFlutter } from "../src/emitters/flutter";
import { parseVue3Component } from "../src/parsers/vue3";
import { parseSvelteComponent } from "../src/parsers/svelte";
import { parseAngularComponent } from "../src/parsers/angular";
import { DialectError, Framework } from "../src/models";

const DASHBOARD = `
function Dashboard({ title, active }: { title: string; active: boolean }) {
  return (
    <section className="dash">
      <header><h1>{title}</h1></header>
      <StatusChip label={title} live={active} />
      <main><UsageChart label={title} /></main>
    </section>
  );
}
`;

const IR = parseReactComponent(DASHBOARD, "Dashboard.tsx");

describe("semantic container tags", () => {
  const TAGS = ["section", "article", "header", "footer", "nav", "main", "aside", "ol", "small", "code"];

  it.each(TAGS)("<%s> is certified and reaches every target", async (tag) => {
    const source = `function C({ t }: { t: string }) { return (<${tag}>{t}</${tag}>); }`;
    const ir = parseReactComponent(source, "C.tsx");
    for (const target of ["vue3", "svelte", "react-native", "miniprogram", "arkui", "flutter"] as const) {
      const report = await translateComponent(emitReact(ir), "react", target, { fileName: "C.tsx", skipExecution: true });
      expect(report.status).toBe("PASSED");
    }
  }, 120000);

  it("still refuses tags with no honest equivalent on the non-web targets", () => {
    // A <table> emitted as nested Columns compiles on Flutter and lays out
    // wrongly -- column sizing, spanning and accessibility all differ. An
    // <form> would silently drop onSubmit on React Native.
    for (const tag of ["table", "tr", "td", "form", "img", "video", "canvas"]) {
      expect(() => parseReactComponent(`function C() { return (<${tag} />); }`, "C.tsx")).toThrow(/UNSUPPORTED_TAG/);
    }
  });
});

describe("a component can render another component", () => {
  it("models the reference rather than mistaking it for an unknown tag", () => {
    expect(referencedComponents(IR)).toEqual(["StatusChip", "UsageChart"]);
  });

  const TARGETS: Framework[] = [
    "typescript", "vue3", "vue2", "angular", "svelte",
    "react-native", "miniprogram", "arkui", "flutter",
  ];

  it.each(TARGETS)("react -> %s passes the target's real compiler", async (target) => {
    const report = await translateComponent(emitReact(IR), "react", target, { fileName: "Dashboard.tsx", skipExecution: true });
    expect(report.status).toBe("PASSED");
    expect(report.validation?.syntaxStatus).toBe("PASSED");
  }, 60000);

  it("uses each framework's own child-reference syntax", () => {
    expect(emitReact(IR)).toContain("<StatusChip label={title} live={active} />");
    expect(emitVue3(IR)).toContain('<StatusChip :label="title" :live="active" />');
    expect(emitSvelte(IR)).toContain("<StatusChip label={title} live={active} />");
    expect(emitArkUI(IR)).toContain("StatusChip({ label: this.title, live: this.active })");
    expect(emitFlutter(IR)).toContain("StatusChip(label: widget.title");
  });

  it("addresses Angular children by SELECTOR, not class name", () => {
    // Angular treats an unknown element as inert: <StatusChip> would
    // compile and render absolutely nothing.
    const angular = emitAngular(IR);
    expect(angular).toContain('<app-status-chip [label]="title" [live]="active"></app-status-chip>');
    expect(angular).not.toContain("<StatusChip");
  });

  it("addresses WeChat children by their kebab-case registered tag", () => {
    const wxml = emitMiniProgram(IR)["wxml"] as string;
    expect(wxml).toContain('<status-chip label="{{ title }}"');
    expect(wxml).not.toContain("<StatusChip");
  });
});

describe("registration, which four targets need and a compiler will not catch", () => {
  it("Angular lists children in the standalone imports array", () => {
    const angular = emitAngular(IR);
    expect(angular).toContain('import { StatusChipComponent } from "./status-chip.component";');
    // Importing the class is NOT enough. Without the imports entry the
    // template compiles and the child renders nothing at all.
    expect(angular).toContain("imports: [CommonModule, StatusChipComponent, UsageChartComponent],");
  });

  it("WeChat registers children in usingComponents", () => {
    // An unregistered custom tag renders as nothing -- no error, no
    // warning, no placeholder anywhere.
    const json = JSON.parse(emitMiniProgram(IR)["json"] as string);
    expect(json.usingComponents).toEqual({
      "status-chip": "/components/StatusChip/index",
      "usage-chart": "/components/UsageChart/index",
    });
  });

  it("Vue 2 declares children in its components map", () => {
    // Vue 3's <script setup> auto-registers; Vue 2's Options API does not,
    // and warns at runtime rather than failing to build.
    const vue2 = emitVue2(IR);
    expect(vue2).toContain('import StatusChip from "./StatusChip.vue";');
    expect(vue2).toContain("components: { StatusChip, UsageChart },");
  });

  it("every ES-module target emits a resolvable sibling import", () => {
    expect(emitReact(IR)).toContain('import StatusChip from "./StatusChip";');
    expect(emitVue3(IR)).toContain('import StatusChip from "./StatusChip.vue";');
    expect(emitSvelte(IR)).toContain('import StatusChip from "./StatusChip.svelte";');
    expect(emitFlutter(IR)).toContain("import 'status_chip.dart';");
  });
});

describe("references round-trip through every list-capable source", () => {
  it("React -> Vue 3 -> canonical is exact", () => {
    expect(parseVue3Component(emitVue3(IR), "Dashboard.vue").root).toEqual(IR.root);
  });

  it("React -> Svelte -> canonical is exact", () => {
    expect(parseSvelteComponent(emitSvelte(IR), "Dashboard.svelte").root).toEqual(IR.root);
  });

  it("React -> Angular -> canonical is exact, selector reversed back to a class name", () => {
    expect(parseAngularComponent(emitAngular(IR), "dashboard.component.ts").root).toEqual(IR.root);
  });
});

describe("composition fails closed outside the certified shape", () => {
  const cases: [string, string][] = [
    ["slot content", `function C({ t }: { t: string }) { return (<div><Child>{t}</Child></div>); }`],
    ["a spread of props", `function C({ t }: { t: string }) { return (<div><Child {...t} /></div>); }`],
    ["a duplicated prop", `function C({ t }: { t: string }) { return (<div><Child a={t} a={t} /></div>); }`],
    ["recursion", `function C({ t }: { t: string }) { return (<div><C t={t} /></div>); }`],
    ["a prop bound to an unsupported call", `function C({ t }: { t: string }) { return (<div><Child a={t.charAt(0)} /></div>); }`],
  ];
  it.each(cases)("blocks %s", (_name, source) => {
    expect(() => parseReactComponent(source, "C.tsx")).toThrow(DialectError);
  });

});

describe("several components in one file", () => {
  const MULTI = `
function Badge({ label }: { label: string }) {
  return (<span className="badge">{label}</span>);
}

function Panel({ heading }: { heading: string }) {
  return (<section><h2>{heading}</h2><Badge label={heading} /></section>);
}
`;

  it("parses them all, in declaration order", () => {
    expect(parseReactComponents(MULTI, "Multi.tsx").map((c) => c.name)).toEqual(["Badge", "Panel"]);
  });

  it("still refuses to guess which one is 'the' component for a single translation", () => {
    expect(() => parseReactComponent(MULTI, "Multi.tsx")).toThrow(/EXPECTED_ONE_FUNCTION/);
  });

  it("rejects two components sharing a name rather than overwriting one", () => {
    const clash = `function A({ x }: { x: string }) { return (<p>{x}</p>); }\nfunction A({ y }: { y: string }) { return (<p>{y}</p>); }\n`;
    expect(() => parseReactComponents(clash, "Clash.tsx")).toThrow(/DUPLICATE_COMPONENT/);
  });

  it("writes every component in the file as its own target file", async () => {
    const repo = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-multi-"));
    fs.mkdirSync(path.join(repo, "src", "components"), { recursive: true });
    fs.writeFileSync(path.join(repo, "src", "components", "Multi.tsx"), MULTI);
    const destination = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-multi-out-"));

    const coverage = await runRepository({ repository: repo, sourceFramework: "react", targetFramework: "vue3", destination, skipExecution: true });
    expect(coverage.totals.converted).toBe(2);
    expect(fs.existsSync(path.join(destination, "src", "components", "Badge.vue"))).toBe(true);
    expect(fs.existsSync(path.join(destination, "src", "components", "Panel.vue"))).toBe(true);
    // Panel renders Badge, and Badge really was produced, so nothing dangles.
    expect(coverage.unresolvedReferences).toEqual([]);
    expect(coverage.deliveryStatus).toBe("ENGINE_COMPLETE");
  }, 120000);

  it("reports one blocked component without blanking out its neighbours", async () => {
    const mixed = `
function Good({ label }: { label: string }) { return (<p>{label}</p>); }
function Bad({ label }: { label: string }) { useEffect(() => {}, []); return (<p>{label}</p>); }
`;
    const repo = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-mixed-"));
    fs.mkdirSync(path.join(repo, "src", "components"), { recursive: true });
    fs.writeFileSync(path.join(repo, "src", "components", "Mixed.tsx"), mixed);
    const destination = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-mixed-out-"));

    const coverage = await runRepository({ repository: repo, sourceFramework: "react", targetFramework: "vue3", destination, skipExecution: true });
    expect(coverage.totals).toMatchObject({ converted: 1, blocked: 1 });
    expect(fs.readFileSync(path.join(destination, "src", "components", "Good.vue"), "utf8")).toContain("{{ label }}");
    expect(fs.readFileSync(path.join(destination, "src", "components", "Bad.vue"), "utf8")).toContain("NOT TRANSLATED");
  }, 120000);
});

describe("a dangling child reference is reported, not left to fail at build time", () => {
  async function runWith(files: Record<string, string>) {
    const repo = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-ref-"));
    fs.mkdirSync(path.join(repo, "src", "components"), { recursive: true });
    for (const [name, contents] of Object.entries(files)) {
      fs.writeFileSync(path.join(repo, "src", "components", name), contents);
    }
    const destination = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-ref-out-"));
    return runRepository({ repository: repo, sourceFramework: "react", targetFramework: "vue3", destination, skipExecution: true });
  }

  it("names a child that no component in the run produced", async () => {
    const coverage = await runWith({
      "Page.tsx": `function Page({ t }: { t: string }) { return (<div><Missing label={t} /></div>); }`,
    });
    // The emitted Page.vue compiles. It imports ./Missing.vue, which does
    // not exist -- a build failure the customer would otherwise meet later,
    // with no explanation of where it came from.
    expect(coverage.unresolvedReferences).toEqual([{
      component: "Missing",
      referencedBy: ["Page"],
      reason: expect.stringContaining("no component of that name was produced"),
    }]);
    expect(coverage.deliveryStatus).toBe("INCOMPLETE");
  }, 120000);

  it("names a child that was itself blocked", async () => {
    const coverage = await runWith({
      "Page.tsx": `function Page({ t }: { t: string }) { return (<div><Chart label={t} /></div>); }`,
      "Chart.tsx": `function Chart({ label }: { label: string }) { useEffect(() => {}, []); return (<div>{label}</div>); }`,
    });
    expect(coverage.unresolvedReferences[0]).toMatchObject({ component: "Chart", referencedBy: ["Page"] });
    expect(coverage.unresolvedReferences[0]?.reason).toMatch(/BLOCKED.*placeholder that throws/);
  }, 120000);

  it("stays silent when every reference resolves", async () => {
    const coverage = await runWith({
      "Page.tsx": `function Page({ t }: { t: string }) { return (<div><Chip label={t} /></div>); }`,
      "Chip.tsx": `function Chip({ label }: { label: string }) { return (<span>{label}</span>); }`,
    });
    expect(coverage.unresolvedReferences).toEqual([]);
    expect(coverage.deliveryStatus).toBe("ENGINE_COMPLETE");
  }, 120000);
});

describe("a named props type declared in the same file", () => {
  it("resolves an interface", () => {
    const source = `
interface Props { label: string; count: number }
function Chip({ label, count }: Props) { return (<span>{label}{count}</span>); }
`;
    const ir = parseReactComponent(source, "Chip.tsx");
    expect(ir.props.map((p) => p.name)).toEqual(["label", "count"]);
  });

  it("resolves a type alias", () => {
    const source = `
type Props = { label: string };
function Chip({ label }: Props) { return (<span>{label}</span>); }
`;
    expect(parseReactComponent(source, "Chip.tsx").props).toHaveLength(1);
  });

  it("refuses a props type this file cannot see", () => {
    // A single-file parser genuinely does not know what an imported name
    // means. Guessing its shape is exactly the kind of invention this
    // engine refuses.
    const source = `
import { Props } from "./types";
function Chip({ label }: Props) { return (<span>{label}</span>); }
`;
    expect(() => parseReactComponent(source, "Chip.tsx")).toThrow(/not declared in this file/);
  });

  it("refuses a generic props type", () => {
    const source = `
interface Props<T> { label: T }
function Chip({ label }: Props<string>) { return (<span>{label}</span>); }
`;
    expect(() => parseReactComponent(source, "Chip.tsx")).toThrow(/generic props type/);
  });

  it("translates a resolved-type component to every target", async () => {
    const source = `
interface Props { label: string }
function Chip({ label }: Props) { return (<span className="chip">{label}</span>); }
`;
    const ir = parseReactComponent(source, "Chip.tsx");
    for (const target of ["vue3", "angular", "svelte", "miniprogram"] as const) {
      const report = await translateComponent(emitReact(ir), "react", target, { fileName: "Chip.tsx", skipExecution: true });
      expect(report.status).toBe("PASSED");
    }
  }, 120000);
});

describe("helper functions are not counted as failed components", () => {
  it("classifies a function that returns no JSX as NOT a component", () => {
    const source = `
function formatLabel(a: string, b: string) { return a + b; }
function Chip({ label }: { label: string }) { return (<span>{label}</span>); }
`;
    const results = parseReactComponentResults(source, "Chip.tsx");
    expect(results[0]?.error?.code).toBe("CERTIFIED_COMPONENT_NOT_A_COMPONENT");
    expect(results[1]?.component?.name).toBe("Chip");
  });

  it("keeps helpers out of the coverage denominator but still reports them", () => {
    // Counting a helper as a failed component is wrong in both directions:
    // it understates coverage, and it fills the blocker ranking with
    // reasons that no amount of subset widening could ever fix.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-helpers-"));
    fs.writeFileSync(path.join(dir, "Chip.tsx"), `
function formatLabel(a: string, b: string) { return a + b; }
function toTitle(s: string) { return s.toUpperCase(); }
function Chip({ label }: { label: string }) { return (<span>{label}</span>); }
`);
    // Imported lazily so this file's other suites do not need the scanner.
    const { scanRepository } = require("../src/scan") as typeof import("../src/scan");
    const report = scanRepository({ repository: dir, sourceFramework: "react", includeAllFindings: true });
    expect(report.totals).toMatchObject({ discovered: 1, inSubset: 1, outOfSubset: 0, notComponents: 2 });
    expect(report.upperBoundCoverage).toBe(1);
    // Excluded, but visible -- never silently dropped.
    expect(report.findings.filter((f) => f.status === "NOT_A_COMPONENT")).toHaveLength(2);
  });
});
