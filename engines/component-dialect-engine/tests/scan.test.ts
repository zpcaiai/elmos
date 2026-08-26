/**
 * Coverage pre-check tests.
 *
 * The pre-check's only value is that its number is trustworthy, so these
 * tests are mostly about the ways a coverage report can lie: shrinking the
 * denominator, hiding engine crashes inside the blocked count, presenting
 * an upper bound as a promise, and burying the ranking that makes the
 * report actionable.
 */
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { renderFeasibilityMarkdown, scanRepository } from "../src/scan";
import { runRepository } from "../src/pipeline";
import { RouteError } from "../src/models";
import { main } from "../src/cli";

const IN_SUBSET = `
function Greeting({ name }: { name: string }) {
  return (<p><span>Hello</span><strong>{name}</strong></p>);
}
`;

const IN_SUBSET_WITH_LIST = `
function Tags({ rows }: { rows: { id: number; label: string }[] }) {
  return (<ul>{rows.map((row) => (<li>{row.label}</li>))}</ul>);
}
`;

/** Blocked by an effect hook -- the single most common real blocker. */
const HOOK = `
function WithEffect({ name }: { name: string }) {
  useEffect(() => { console.log(name); }, [name]);
  return (<p>{name}</p>);
}
`;

const ANOTHER_HOOK = `
function AlsoWithEffect({ name }: { name: string }) {
  useEffect(() => { console.log(name); }, [name]);
  return (<span>{name}</span>);
}
`;

/** Blocked by a prop type outside the certified set. */
const OBJECT_PROP = `
function Profile({ user }: { user: { name: string } }) {
  return (<p>{user}</p>);
}
`;

/** Not a component at all -- a helper module that happens to be .tsx. */
const NOT_A_COMPONENT = `
export function formatName(a: string, b: string) { return a + b; }
export function joinName(a: string, b: string) { return a + " " + b; }
`;

function makeRepo(files: Record<string, string>): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-scan-"));
  for (const [name, contents] of Object.entries(files)) {
    const full = path.join(dir, "src", "components", name);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, contents);
  }
  return dir;
}

const REPO = () => makeRepo({
  "Greeting.tsx": IN_SUBSET,
  "Tags.tsx": IN_SUBSET_WITH_LIST,
  "WithEffect.tsx": HOOK,
  "AlsoWithEffect.tsx": ANOTHER_HOOK,
  "Profile.tsx": OBJECT_PROP,
  "helpers.tsx": NOT_A_COMPONENT,
});

describe("the headline number is a real count", () => {
  it("counts every discovered component, in subset and out", () => {
    const report = scanRepository({ repository: REPO(), sourceFramework: "react" });
    // Counted per COMPONENT. helpers.tsx holds two functions that return no
    // JSX, so they are helpers rather than failed components and sit outside
    // the denominator.
    expect(report.totals).toEqual({ discovered: 5, inSubset: 2, outOfSubset: 3, scanErrors: 0, notComponents: 2 });
    expect(report.upperBoundCoverage).toBeCloseTo(2 / 5, 3);
  });

  it("excludes helper functions from the ratio but still reports them", () => {
    // Two failure modes to avoid. Counting a helper as a failed component
    // understates coverage and fills the blocker ranking with reasons no
    // widening could fix; dropping it silently makes the exclusion
    // unauditable. So: excluded from the denominator, listed in findings.
    const report = scanRepository({ repository: REPO(), sourceFramework: "react", includeAllFindings: true });
    const helpers = report.findings.filter((f) => f.sourcePath.endsWith("helpers.tsx"));
    expect(helpers).toHaveLength(2);
    for (const helper of helpers) {
      expect(helper.status).toBe("NOT_A_COMPONENT");
      expect(helper.reasonCode).toBe("CERTIFIED_COMPONENT_NOT_A_COMPONENT");
    }
    expect(report.totals.notComponents).toBe(2);
  });

  it("never drops a real component from the denominator", () => {
    // Every discovered component is either in subset or out -- nothing that
    // returns JSX may quietly vanish to flatter the ratio.
    const report = scanRepository({ repository: REPO(), sourceFramework: "react", includeAllFindings: true });
    const components = report.findings.filter((f) => f.status === "IN_SUBSET" || f.status === "OUT_OF_SUBSET");
    expect(components).toHaveLength(report.totals.discovered);
    expect(report.totals.inSubset + report.totals.outOfSubset).toBe(report.totals.discovered);
  });

  it("reports 0 rather than dividing by zero on an empty repository", () => {
    const report = scanRepository({ repository: makeRepo({}), sourceFramework: "react" });
    expect(report.totals.discovered).toBe(0);
    expect(report.upperBoundCoverage).toBe(0);
    expect(report.blockers).toEqual([]);
  });
});

describe("blockers are ranked so the report is actionable", () => {
  it("puts the most frequent blocker first with an exact count", () => {
    const report = scanRepository({ repository: REPO(), sourceFramework: "react" });
    expect(report.blockers[0]).toMatchObject({
      reasonCode: "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT",
      count: 2,
      family: "structure",
    });
    expect(report.blockers.map((b) => b.count)).toEqual([...report.blockers.map((b) => b.count)].sort((a, b) => b - a));
  });

  it("explains each blocker in words, not just a reason code", () => {
    const report = scanRepository({ repository: REPO(), sourceFramework: "react" });
    for (const blocker of report.blockers) {
      expect(blocker.what.length).toBeGreaterThan(20);
      expect(blocker.what).not.toMatch(/^CERTIFIED_COMPONENT_/);
    }
  });

  it("names example files but keeps the count exact when it caps them", () => {
    const report = scanRepository({ repository: REPO(), sourceFramework: "react", examplesPerBlocker: 1 });
    const hooks = report.blockers.find((b) => b.reasonCode === "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT");
    expect(hooks?.count).toBe(2);
    expect(hooks?.exampleFiles).toHaveLength(1);
    expect(report.blockers.every((b) => b.exampleFiles.length <= 1)).toBe(true);
  });

  it("is deterministic so two scans of the same tree diff cleanly", () => {
    const repo = REPO();
    const a = scanRepository({ repository: repo, sourceFramework: "react" });
    const b = scanRepository({ repository: repo, sourceFramework: "react" });
    expect(a.blockers).toEqual(b.blockers);
    expect(a.families).toEqual(b.families);
  });

  it("rolls blockers up into families", () => {
    const report = scanRepository({ repository: REPO(), sourceFramework: "react" });
    const total = report.families.reduce((sum, f) => sum + f.count, 0);
    expect(total).toBe(report.totals.outOfSubset);
  });
});

describe("the number is presented as an upper bound, not a promise", () => {
  it("states the upper-bound caveat in the report itself", () => {
    const report = scanRepository({ repository: REPO(), sourceFramework: "react" });
    expect(report.caveats.join(" ")).toMatch(/UPPER BOUND/);
    expect(report.caveats.join(" ")).toMatch(/re-validated by the target framework's own compiler/);
  });

  it("the upper bound really does bound a real run", async () => {
    // The claim is only worth making if it holds against the actual
    // pipeline, so this asserts it rather than asserting the wording.
    const repo = REPO();
    const scan = scanRepository({ repository: repo, sourceFramework: "react" });
    const destination = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-scan-out-"));
    const coverage = await runRepository({
      repository: repo, sourceFramework: "react", targetFramework: "vue3", destination, skipExecution: true,
    });
    expect(coverage.totals.discovered).toBe(scan.totals.discovered);
    expect(coverage.totals.converted).toBeLessThanOrEqual(scan.totals.inSubset);
  }, 120000);
});

describe("engine defects are never laundered into the coverage number", () => {
  it("counts a compiler rejection as a subset boundary, not an engine error", () => {
    // @vue/compiler-sfc really does reject this, and that is PARSE_FAILED
    // -- a fact about the input. It must not inflate scanErrors, which is
    // reserved for defects in this engine.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-scan-broken-"));
    fs.writeFileSync(path.join(dir, "Broken.vue"), '<template><div v-if></template>\n<script setup lang="ts">\nconst');
    const report = scanRepository({ repository: dir, sourceFramework: "vue3" });
    expect(report.totals).toMatchObject({ discovered: 1, outOfSubset: 1, scanErrors: 0 });
    expect(report.findings[0]?.reasonCode).toBe("CERTIFIED_COMPONENT_PARSE_FAILED");
    expect(report.findings[0]?.family).toBe("source-format");
  });

  it("does not crash on a malformed .tsx, because TypeScript's parser recovers", () => {
    // TypeScript's parser is deliberately error-tolerant: it builds a tree
    // from broken input rather than throwing. So a malformed component
    // surfaces as whichever certified-subset check fires first, NOT as
    // PARSE_FAILED. Worth pinning down -- it means "syntactically invalid"
    // and "outside the subset" are not distinguishable for TS sources, and
    // a reader of the report should not infer otherwise.
    const repo = makeRepo({ "Broken.tsx": "function Broken( { return (<p>;" });
    const report = scanRepository({ repository: repo, sourceFramework: "react", includeAllFindings: true });
    expect(report.totals.scanErrors).toBe(0);
    // TypeScript recovers so thoroughly that the mangled JSX disappears and
    // the function reads as a helper. Pinned because it is a real limit of
    // scanning TS sources, and it is stated in the report's caveats rather
    // than left for a reader to discover.
    expect(report.findings[0]?.reasonCode).toBe("CERTIFIED_COMPONENT_NOT_A_COMPONENT");
    expect(report.caveats.join(" ")).toMatch(/error-tolerant/);
  });

  it("puts a scan-error warning first in the caveats when one occurs", () => {
    const report = scanRepository({ repository: REPO(), sourceFramework: "react" });
    expect(report.totals.scanErrors).toBe(0);
    // The warning is conditional; with zero errors it must be absent, so a
    // clean report is not padded with a scary non-issue.
    expect(report.caveats[0]).not.toMatch(/SCAN_ERROR/);
  });
});

describe("scanning refuses what it cannot honestly answer", () => {
  it("resolves an imported props alias through the real TypeScript project checker", () => {
    const repo = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-scan-imported-type-"));
    fs.writeFileSync(path.join(repo, "tsconfig.json"), JSON.stringify({
      compilerOptions: { target: "ES2022", module: "CommonJS", jsx: "react", strict: true, skipLibCheck: true },
      include: ["**/*.ts", "**/*.tsx"],
    }));
    fs.writeFileSync(path.join(repo, "types.ts"), "export interface CardProps { title: string }\n");
    fs.writeFileSync(path.join(repo, "Card.tsx"), "import type { CardProps } from './types';\nfunction Card({ title }: CardProps) { return <p>{title}</p>; }\n");
    const report = scanRepository({ repository: repo, sourceFramework: "react" });
    expect(report.totals).toMatchObject({ discovered: 1, inSubset: 1, outOfSubset: 0, scanErrors: 0 });
  });

  it("allows a declared object prop only through a declared field", () => {
    const repo = makeRepo({
      "Profile.tsx": "function Profile({ user }: { user: { name: string } }) { return <p>{user.name}</p>; }",
    });
    const report = scanRepository({ repository: repo, sourceFramework: "react" });
    expect(report.totals.inSubset).toBe(1);
  });

  it("rejects emit-only frameworks as a scan source", () => {
    expect(() => scanRepository({ repository: REPO(), sourceFramework: "flutter" })).toThrow(/FRAMEWORK_NOT_PARSEABLE/);
    expect(() => scanRepository({ repository: REPO(), sourceFramework: "arkui" })).toThrow(RouteError);
  });

  it("rejects a repository that does not exist", () => {
    expect(() => scanRepository({ repository: "/nonexistent/elmos", sourceFramework: "react" })).toThrow(/REPOSITORY_NOT_FOUND/);
  });

  it("reads a WeChat component as the .wxml + .js pair it really is", () => {
    const repo = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-scan-mp-"));
    const dir = path.join(repo, "components", "Orphan");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "index.wxml"), "<view>x</view>\n");
    const report = scanRepository({ repository: repo, sourceFramework: "miniprogram" });
    expect(report.findings[0]?.reasonCode).toBe("CERTIFIED_COMPONENT_MISSING_SCRIPT");
    expect(report.findings[0]?.family).toBe("source-format");
  });
});

describe("dogfood: scanning real in-tree application code", () => {
  // apps/web-console is a genuine Next.js/React application in this
  // monorepo -- not a fixture written to pass. Scanning it is the only
  // check here that exercises code nobody shaped for the subset.
  //
  // At the time of writing it scores 0 of 28. That number is deliberately
  // NOT asserted: it will move as the subset widens and as the console
  // evolves, and pinning it would turn an honest measurement into a test
  // to be gamed. What IS asserted is the part that must never regress --
  // real application code produces zero engine errors, and every blocked
  // file carries an actionable reason.
  const consoleDir = path.resolve(__dirname, "..", "..", "..", "apps", "web-console");
  const dogfood = fs.existsSync(consoleDir) ? it : it.skip;

  dogfood("parses real application code without a single engine error", () => {
    const report = scanRepository({ repository: consoleDir, sourceFramework: "react" });
    expect(report.totals.discovered).toBeGreaterThan(0);
    // A crash on real code is a defect in this engine, and it must never
    // be able to hide inside the coverage percentage.
    expect(report.totals.scanErrors).toBe(0);
  }, 120000);

  dogfood("gives every blocked real-world file a mapped, explained reason", () => {
    const report = scanRepository({ repository: consoleDir, sourceFramework: "react" });
    for (const finding of report.findings) {
      expect(finding.reasonCode).toBeTruthy();
      // An unmapped family means real code hit a reason code the catalog
      // never described -- the report would still be correct, but the
      // reader would be handed a bare identifier instead of an
      // explanation.
      expect(finding.family).not.toBeNull();
    }
    for (const blocker of report.blockers) expect(blocker.what).not.toBe("no description available");
  }, 120000);
});

describe("the report reaches a human, not only a machine", () => {
  it("renders markdown carrying the count, the ranking and the caveat", () => {
    const markdown = renderFeasibilityMarkdown(scanRepository({ repository: REPO(), sourceFramework: "react" }));
    expect(markdown).toContain("2 of 5 discovered components are inside the certified subset");
    expect(markdown).toContain("40.0%");
    expect(markdown).toContain("CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT");
    expect(markdown).toContain("UPPER BOUND");
  });

  it("writes both formats and exits non-zero when coverage is incomplete", async () => {
    const out = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-scan-cli-"));
    const log = jest.spyOn(console, "log").mockImplementation(() => {});
    try {
      const code = await main(["scan", "--repository", REPO(), "--source-framework", "react", "--output", out]);
      expect(code).toBe(2);
    } finally {
      log.mockRestore();
    }
    const json = JSON.parse(fs.readFileSync(path.join(out, "feasibility-report.json"), "utf8"));
    expect(json.kind).toBe("elmos.component-dialect-feasibility-scan");
    expect(fs.existsSync(path.join(out, "feasibility-report.md"))).toBe(true);
  }, 60000);

  it("exits 0 only when every discovered component is in subset", async () => {
    const repo = makeRepo({ "Greeting.tsx": IN_SUBSET, "Tags.tsx": IN_SUBSET_WITH_LIST });
    const log = jest.spyOn(console, "log").mockImplementation(() => {});
    try {
      expect(await main(["scan", "--repository", repo, "--source-framework", "react"])).toBe(0);
    } finally {
      log.mockRestore();
    }
  }, 60000);
});
