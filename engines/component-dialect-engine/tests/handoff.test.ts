/**
 * Human handoff tests.
 *
 * These are mostly about data loss and silent staleness, because those are
 * the two ways a handoff feature hurts people: it overwrites a week of
 * hand-written code, or it lets a hand port quietly drift away from the
 * source it was derived from and keep shipping.
 */
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { runRepository } from "../src/pipeline";
import { assign, loadManifest, markPorted, unmark } from "../src/handoff";
import { RouteError } from "../src/models";
import { main } from "../src/cli";

const IN_SUBSET = `
function Greeting({ name }: { name: string }) {
  return (<p><span>Hello</span><strong>{name}</strong></p>);
}
`;

/** Outside the subset -- an effect hook. This is the component a human
 * has to take over. */
const BLOCKED = `
function Chart({ label }: { label: string }) {
  useEffect(() => { console.log(label); }, [label]);
  return (<div>{label}</div>);
}
`;

const HAND_WRITTEN = `<script setup lang="ts">
// Ported by hand: renders a real chart the engine cannot express.
defineProps<{ label: string }>();
</script>

<template>
  <div class="chart">hand written</div>
</template>
`;

function makeRepo(files: Record<string, string> = { "Greeting.tsx": IN_SUBSET, "Chart.tsx": BLOCKED }): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-ho-src-"));
  for (const [name, contents] of Object.entries(files)) {
    const full = path.join(dir, "src", "components", name);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, contents);
  }
  return dir;
}

const CHART_SOURCE = path.join("src", "components", "Chart.tsx");
const CHART_TARGET = path.join("src", "components", "Chart.vue");

async function convert(repository: string, destination: string) {
  return runRepository({ repository, sourceFramework: "react", targetFramework: "vue3", destination, skipExecution: true });
}

/** First run, then a human ports Chart by hand and marks it. */
async function migrationWithHandPort(): Promise<{ repo: string; destination: string }> {
  const repo = makeRepo();
  const destination = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-ho-out-"));
  await convert(repo, destination);
  fs.writeFileSync(path.join(destination, CHART_TARGET), HAND_WRITTEN);
  markPorted({ destination, repository: repo, sourcePath: CHART_SOURCE, targetPath: CHART_TARGET, assignee: "dana" });
  return { repo, destination };
}

describe("a re-run never destroys hand-written code", () => {
  it("leaves the hand-written file byte-for-byte untouched", async () => {
    const { repo, destination } = await migrationWithHandPort();
    await convert(repo, destination);
    // The placeholder would have thrown "NOT TRANSLATED" here.
    expect(fs.readFileSync(path.join(destination, CHART_TARGET), "utf8")).toBe(HAND_WRITTEN);
  }, 120000);

  it("reports it as MANUALLY_PORTED, not CONVERTED and not BLOCKED", async () => {
    const { repo, destination } = await migrationWithHandPort();
    const coverage = await convert(repo, destination);
    const chart = coverage.files.find((f) => f.sourcePath === CHART_SOURCE);
    expect(chart?.status).toBe("MANUALLY_PORTED");
    expect(coverage.totals).toEqual({ discovered: 2, converted: 1, blocked: 0, manuallyPorted: 1 });
  }, 120000);

  it("still overwrites files nobody claimed", async () => {
    const { repo, destination } = await migrationWithHandPort();
    const greeting = path.join(destination, "src", "components", "Greeting.vue");
    fs.writeFileSync(greeting, "// scribble\n");
    await convert(repo, destination);
    // Protection is opt-in per component. An unmarked file is the
    // engine's, and pretending otherwise would make re-runs useless.
    expect(fs.readFileSync(greeting, "utf8")).not.toBe("// scribble\n");
  }, 120000);

  it("hands the file back to the engine after unmark", async () => {
    const { repo, destination } = await migrationWithHandPort();
    unmark(destination, CHART_SOURCE);
    const coverage = await convert(repo, destination);
    expect(coverage.files.find((f) => f.sourcePath === CHART_SOURCE)?.status).toBe("BLOCKED");
    expect(fs.readFileSync(path.join(destination, CHART_TARGET), "utf8")).toContain("NOT TRANSLATED");
  }, 120000);
});

describe("a stale hand port is loud, never silent", () => {
  it("flags SOURCE_CHANGED_SINCE_PORT when the source moves on", async () => {
    const { repo, destination } = await migrationWithHandPort();
    // The dangerous case: upstream changes, the hand port does not, and
    // the app keeps rendering last month's behavior.
    fs.writeFileSync(path.join(repo, CHART_SOURCE), BLOCKED.replace("console.log(label)", "console.log(label, 2)"));
    const coverage = await convert(repo, destination);
    const chart = coverage.files.find((f) => f.sourcePath === CHART_SOURCE);
    expect(chart?.handoffAlerts).toContain("SOURCE_CHANGED_SINCE_PORT");
    expect(chart?.notes.join(" ")).toMatch(/stale/);
  }, 120000);

  it("keeps delivery INCOMPLETE while a port is stale", async () => {
    const { repo, destination } = await migrationWithHandPort();
    // With nothing stale, every component is handled, so delivery is
    // complete-with-handoff.
    expect((await convert(repo, destination)).deliveryStatus).toBe("COMPLETE_WITH_HANDOFF");

    fs.writeFileSync(path.join(repo, CHART_SOURCE), BLOCKED.replace("label", "caption"));
    const after = await convert(repo, destination);
    expect(after.deliveryStatus).toBe("INCOMPLETE");
    expect(after.handoff.stale).toBe(1);
  }, 180000);

  it("flags a hand-ported file that has gone missing", async () => {
    const { repo, destination } = await migrationWithHandPort();
    fs.unlinkSync(path.join(destination, CHART_TARGET));
    const coverage = await convert(repo, destination);
    expect(coverage.files.find((f) => f.sourcePath === CHART_SOURCE)?.handoffAlerts).toContain("PORTED_FILE_MISSING");
    expect(coverage.deliveryStatus).toBe("INCOMPLETE");
  }, 120000);

  it("reports, but does not act on, a component the engine could now convert", async () => {
    // A hand port of something inside the subset. Overwriting it is the
    // human's call, not the tool's -- the hand version may exist precisely
    // because the automatic one was not good enough.
    const repo = makeRepo({ "Greeting.tsx": IN_SUBSET });
    const destination = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-ho-auto-"));
    await convert(repo, destination);
    const target = path.join("src", "components", "Greeting.vue");
    fs.writeFileSync(path.join(destination, target), HAND_WRITTEN);
    markPorted({ destination, repository: repo, sourcePath: path.join("src", "components", "Greeting.tsx"), targetPath: target });

    const coverage = await convert(repo, destination);
    expect(coverage.files[0]?.handoffAlerts).toContain("AUTOMATIC_CONVERSION_NOW_AVAILABLE");
    expect(fs.readFileSync(path.join(destination, target), "utf8")).toBe(HAND_WRITTEN);
    // An advisory alert alone must not hold delivery open.
    expect(coverage.deliveryStatus).toBe("COMPLETE_WITH_HANDOFF");
  }, 180000);
});

describe("hand work is never counted as engine evidence", () => {
  it("keeps the engine-level status PARTIAL even when everything is handled", async () => {
    const { repo, destination } = await migrationWithHandPort();
    const coverage = await convert(repo, destination);
    // Nothing is blocked, yet the engine converted only 1 of 2 -- so the
    // engine-level status must not read COMPLETE.
    expect(coverage.status).toBe("PARTIAL");
    expect(coverage.deliveryStatus).toBe("COMPLETE_WITH_HANDOFF");
  }, 120000);

  it("records no syntax or execution evidence for a hand-ported file", async () => {
    const { repo, destination } = await migrationWithHandPort();
    const chart = (await convert(repo, destination)).files.find((f) => f.sourcePath === CHART_SOURCE);
    expect(chart?.syntaxStatus).toBeNull();
    expect(chart?.executionStatus).toBeNull();
  }, 120000);

  it("reports ENGINE_COMPLETE only for a pure engine run", async () => {
    const repo = makeRepo({ "Greeting.tsx": IN_SUBSET });
    const destination = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-ho-pure-"));
    const coverage = await convert(repo, destination);
    expect(coverage.deliveryStatus).toBe("ENGINE_COMPLETE");
    expect(coverage.status).toBe("COMPLETE");
  }, 120000);
});

describe("the manifest refuses to lose marks", () => {
  it("refuses to run on a corrupt manifest rather than treating it as empty", async () => {
    const { repo, destination } = await migrationWithHandPort();
    fs.writeFileSync(path.join(destination, "handoff.json"), "{ not json");
    // Silently starting fresh would un-protect every hand-ported file --
    // the exact data loss this module exists to prevent.
    await expect(convert(repo, destination)).rejects.toThrow(/HANDOFF_MANIFEST_UNREADABLE/);
  }, 120000);

  it("refuses a mark whose target file does not exist", async () => {
    const repo = makeRepo();
    const destination = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-ho-nofile-"));
    await convert(repo, destination);
    expect(() => markPorted({
      destination, repository: repo, sourcePath: CHART_SOURCE, targetPath: path.join("src", "components", "Nope.vue"),
    })).toThrow(/HANDOFF_TARGET_NOT_FOUND/);
  }, 120000);

  it("refuses to reassign a ported component without unmarking first", async () => {
    const { destination } = await migrationWithHandPort();
    expect(() => assign({ destination, sourcePath: CHART_SOURCE, assignee: "sam" })).toThrow(/HANDOFF_ALREADY_PORTED/);
  }, 120000);

  it("keeps the manifest sorted so it diffs cleanly in review", async () => {
    const { destination } = await migrationWithHandPort();
    assign({ destination, sourcePath: path.join("src", "components", "AAA.tsx"), assignee: "sam" });
    const paths = loadManifest(destination).entries.map((e) => e.sourcePath);
    expect(paths).toEqual([...paths].sort());
  }, 120000);

  it("rejects an unmark of something that was never tracked", async () => {
    const { destination } = await migrationWithHandPort();
    expect(() => unmark(destination, "src/components/Ghost.tsx")).toThrow(RouteError);
  }, 120000);
});

describe("handoff is drivable from the CLI", () => {
  it("assigns, marks, and reports status", async () => {
    const repo = makeRepo();
    const destination = fs.mkdtempSync(path.join(os.tmpdir(), "elmos-ho-cli-"));
    await convert(repo, destination);
    const log = jest.spyOn(console, "log").mockImplementation(() => {});
    try {
      expect(await main(["handoff", "assign", "--destination", destination, "--source-path", CHART_SOURCE, "--assignee", "dana", "--note", "needs the real chart lib"])).toBe(0);
      fs.writeFileSync(path.join(destination, CHART_TARGET), HAND_WRITTEN);
      expect(await main(["handoff", "mark-ported", "--destination", destination, "--repository", repo, "--source-path", CHART_SOURCE, "--target-path", CHART_TARGET])).toBe(0);
      expect(await main(["handoff", "status", "--destination", destination])).toBe(0);
    } finally {
      log.mockRestore();
    }

    const entry = loadManifest(destination).entries.find((e) => e.sourcePath === CHART_SOURCE);
    expect(entry).toMatchObject({ state: "MANUALLY_PORTED", assignee: "dana", note: "needs the real chart lib" });
    expect(entry?.sourceHashAtPort).toMatch(/^[0-9a-f]{64}$/);
  }, 180000);

  it("rejects an unknown handoff subcommand instead of doing something surprising", async () => {
    const log = jest.spyOn(console, "log").mockImplementation(() => {});
    try {
      expect(await main(["handoff", "delete-everything", "--destination", "/tmp"])).toBe(2);
    } finally {
      log.mockRestore();
    }
  });
});
