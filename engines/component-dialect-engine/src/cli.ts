#!/usr/bin/env node
/**
 * CLI for certified-component-v1.
 *
 *   scan        -- parse-only feasibility pre-check: how much of a
 *                  repository is inside the subset, and what is blocking
 *                  the rest. Writes nothing, picks no target.
 *   translate   -- one component, one direction, full evidence report
 *   repository  -- whole project, producing a target project that builds,
 *                  plus coverage-report.json
 *   handoff     -- assign blocked components to people, mark them
 *                  hand-ported, and protect that work from re-runs
 *
 * Follows the same convention as `engines/sql-dialect-engine`'s CLI:
 * a caller mistake (RouteError) prints a BLOCKED JSON document and exits 2
 * rather than dumping a stack trace.
 */
import * as fs from "fs";
import * as path from "path";
import { ALL_FRAMEWORKS, Framework, RouteError } from "./models";
import { resolveFramework, translateComponent } from "./engine";
import { runRepository } from "./pipeline";
import { renderFeasibilityMarkdown, scanRepository } from "./scan";
import { assign, loadManifest, markPorted, summarize, unmark } from "./handoff";
import { bindEvidenceObservation, validateEvidenceLedger } from "./evidence";
import { verifyBuild } from "./verify";

interface Args {
  command: string;
  values: Record<string, string>;
  flags: Set<string>;
}

function parseArgs(argv: string[]): Args {
  const [command = "", ...rest] = argv;
  const values: Record<string, string> = {};
  const flags = new Set<string>();
  for (let i = 0; i < rest.length; i++) {
    const token = rest[i] as string;
    // `handoff assign --...` -- the leading bare word is the subcommand.
    if (!token.startsWith("--")) {
      if (i === 0) values["_sub"] = token;
      continue;
    }
    const key = token.slice(2);
    const next = rest[i + 1];
    if (next === undefined || next.startsWith("--")) { flags.add(key); continue; }
    values[key] = next;
    i++;
  }
  return { command, values, flags };
}

function required(args: Args, key: string): string {
  const value = args.values[key];
  if (value === undefined) throw new RouteError(`MISSING_ARGUMENT: --${key} is required`);
  return value;
}

const USAGE = `elmos-component-dialect <command> [options]

Commands:
  scan        --repository <dir> --source-framework <f>
              [--output <dir>] [--examples <n>] [--all-findings]
              Feasibility pre-check. Parses every component and reports how
              many are inside certified-component-v1, ranked by blocker.
              Exits 0 when every component is in subset, 2 otherwise.

  translate   --source-file <path> --source-framework <f> --target-framework <f>
              [--output <dir>] [--skip-execution]

  repository  --repository <dir> --source-framework <f> --target-framework <f>
              --destination <dir> [--skip-execution] [--verify]

  handoff     assign      --destination <dir> --source-path <p> [--component-name <n>] --assignee <who> [--note <text>]
              mark-ported --destination <dir> --repository <dir> --source-path <p> --target-path <p>
                          [--component-name <n>] [--assignee <who>] [--note <text>]
              unmark      --destination <dir> --source-path <p> [--component-name <n>]
              status      --destination <dir>
              A component marked hand-ported is never overwritten by a
              later 'repository' run, and that run reports it stale if
              its SOURCE changed after the port.

  evidence    init        --source-file <path> --source-framework <f> --target-framework <f>
                          --output <dir> [--skip-execution]
              validate    --file <evidence-ledger.json>
              bind        --file <evidence-ledger.json> --record-id <id>
                          --status PASSED|FAILED --artifact-file <path> --executor <id>
                          [--verifier <id>] [--independent] [--note <text>]
              init creates a NOT_CERTIFIED ledger. bind hashes the supplied
              artifact bytes and keeps the claim NOT_CERTIFIED; it records
              evidence but cannot manufacture a release or certification decision.

Frameworks: ${ALL_FRAMEWORKS.join(", ")}
  Parseable as a SOURCE: react, typescript, react-native, vue3
  (arkui and flutter are emit-only; see README for why.)
`;

/**
 * The pre-check exists so a customer learns the coverage number BEFORE
 * committing to a migration, not from the wreckage of a failed run. It is
 * parse-only and takes no target framework: subset membership is a
 * property of the source.
 */
function commandScan(args: Args): number {
  const report = scanRepository({
    repository: required(args, "repository"),
    sourceFramework: resolveFramework(required(args, "source-framework")),
    examplesPerBlocker: args.values["examples"] ? Number(args.values["examples"]) : undefined,
    includeAllFindings: args.flags.has("all-findings"),
  });

  const outDir = args.values["output"];
  if (outDir) {
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, "feasibility-report.json"), JSON.stringify(report, null, 2) + "\n");
    // The migration decision gets made by someone who will not read JSON.
    fs.writeFileSync(path.join(outDir, "feasibility-report.md"), renderFeasibilityMarkdown(report));
  }

  console.log(JSON.stringify(report, null, 2));
  return report.totals.outOfSubset === 0 && report.totals.scanErrors === 0 ? 0 : 2;
}

async function commandTranslate(args: Args): Promise<number> {
  const sourceFile = required(args, "source-file");
  const report = await translateComponent(
    fs.readFileSync(sourceFile, "utf8"),
    required(args, "source-framework"),
    required(args, "target-framework"),
    { fileName: path.basename(sourceFile), skipExecution: args.flags.has("skip-execution") },
  );

  const outDir = args.values["output"];
  if (outDir) {
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, "translation-report.json"), JSON.stringify(report, null, 2) + "\n");
    if (report.emitted !== null) fs.writeFileSync(path.join(outDir, "emitted.txt"), report.emitted);
    if (report.emittedFiles !== null) {
      for (const [ext, contents] of Object.entries(report.emittedFiles)) {
        fs.writeFileSync(path.join(outDir, `emitted.${ext}`), contents);
      }
    }
  }
  console.log(JSON.stringify(report, null, 2));
  return report.status === "PASSED" ? 0 : 2;
}

async function commandRepository(args: Args): Promise<number> {
  const target = resolveFramework(required(args, "target-framework"));
  const destination = required(args, "destination");
  const coverage = await runRepository({
    repository: required(args, "repository"),
    sourceFramework: resolveFramework(required(args, "source-framework")),
    targetFramework: target,
    destination,
    skipExecution: args.flags.has("skip-execution"),
  });

  let verification = null;
  if (args.flags.has("verify")) {
    verification = verifyBuild(destination, target);
    fs.writeFileSync(path.join(destination, "build-verification.json"), JSON.stringify(verification, null, 2) + "\n");
  }

  console.log(JSON.stringify({ coverage, verification }, null, 2));
  if (verification && verification.status === "FAILED") return 2;
  return coverage.status === "COMPLETE" ? 0 : 2;
}

/**
 * Handoff is what lets a migration continue past the subset boundary
 * instead of stopping there. The marks it writes are load-bearing: a
 * later `repository` run reads them and skips those files entirely.
 */
function commandHandoff(args: Args): number {
  const sub = args.values["_sub"] ?? "";
  if (sub === "assign") {
    const entry = assign({
      destination: required(args, "destination"),
      sourcePath: required(args, "source-path"),
      ...(args.values["component-name"] !== undefined ? { componentName: args.values["component-name"] } : {}),
      assignee: required(args, "assignee"),
      ...(args.values["note"] !== undefined ? { note: args.values["note"] } : {}),
    });
    console.log(JSON.stringify(entry, null, 2));
    return 0;
  }
  if (sub === "mark-ported") {
    const entry = markPorted({
      destination: required(args, "destination"),
      repository: required(args, "repository"),
      sourcePath: required(args, "source-path"),
      ...(args.values["component-name"] !== undefined ? { componentName: args.values["component-name"] } : {}),
      targetPath: required(args, "target-path"),
      ...(args.values["assignee"] !== undefined ? { assignee: args.values["assignee"] } : {}),
      ...(args.values["note"] !== undefined ? { note: args.values["note"] } : {}),
    });
    console.log(JSON.stringify(entry, null, 2));
    return 0;
  }
  if (sub === "unmark") {
    console.log(JSON.stringify(unmark(
      required(args, "destination"),
      required(args, "source-path"),
      args.values["component-name"],
    ), null, 2));
    return 0;
  }
  if (sub === "status") {
    const manifest = loadManifest(required(args, "destination"));
    // Staleness needs a source tree to compare against, so `status` alone
    // reports counts and says so rather than implying it checked.
    console.log(JSON.stringify({
      summary: summarize(manifest, []),
      entries: manifest.entries,
      note: "Staleness is evaluated during a `repository` run, which has the source tree to compare against.",
    }, null, 2));
    return 0;
  }
  throw new RouteError(`UNKNOWN_HANDOFF_SUBCOMMAND: ${JSON.stringify(sub)} is not assign, mark-ported, unmark or status`);
}

async function commandEvidence(args: Args): Promise<number> {
  const sub = args.values["_sub"] ?? "";
  if (sub === "init") {
    const sourceFile = required(args, "source-file");
    const report = await translateComponent(
      fs.readFileSync(sourceFile, "utf8"),
      required(args, "source-framework"),
      required(args, "target-framework"),
      { fileName: path.basename(sourceFile), skipExecution: args.flags.has("skip-execution") },
    );
    const output = required(args, "output");
    fs.mkdirSync(output, { recursive: true });
    fs.writeFileSync(path.join(output, "translation-report.json"), JSON.stringify(report, null, 2) + "\n");
    if (report.semanticIR !== null) fs.writeFileSync(path.join(output, "semantic-ir.json"), JSON.stringify(report.semanticIR, null, 2) + "\n");
    if (report.evidence !== null) fs.writeFileSync(path.join(output, "evidence-ledger.json"), JSON.stringify(report.evidence, null, 2) + "\n");
    console.log(JSON.stringify({ status: report.status, reasonCode: report.reasonCode, output }, null, 2));
    return report.status === "PASSED" ? 0 : 2;
  }
  if (sub === "validate") {
    const file = required(args, "file");
    const ledger = JSON.parse(fs.readFileSync(file, "utf8")) as Parameters<typeof validateEvidenceLedger>[0];
    const errors = validateEvidenceLedger(ledger);
    console.log(JSON.stringify({ valid: errors.length === 0, errors }, null, 2));
    return errors.length === 0 ? 0 : 2;
  }
  if (sub === "bind") {
    const file = required(args, "file");
    const ledger = JSON.parse(fs.readFileSync(file, "utf8")) as Parameters<typeof bindEvidenceObservation>[0];
    const artifactFile = required(args, "artifact-file");
    const status = required(args, "status");
    if (status !== "PASSED" && status !== "FAILED") throw new RouteError("EVIDENCE_STATUS_INVALID: status must be PASSED or FAILED");
    let updated;
    try {
      updated = bindEvidenceObservation(ledger, required(args, "record-id"), {
        status,
        artifactPath: artifactFile,
        artifactContents: fs.readFileSync(artifactFile, "utf8"),
        executor: required(args, "executor"),
        ...(args.values["verifier"] !== undefined ? { verifier: args.values["verifier"] } : {}),
        ...(args.flags.has("independent") ? { independent: true } : {}),
        ...(args.values["note"] !== undefined ? { notes: [args.values["note"]] } : {}),
      });
    } catch (error) {
      throw new RouteError(error instanceof Error ? error.message : "EVIDENCE_LEDGER_INVALID");
    }
    fs.writeFileSync(file, JSON.stringify(updated, null, 2) + "\n");
    console.log(JSON.stringify({ file, claim: updated.claim, unresolved: updated.unresolved }, null, 2));
    return 0;
  }
  throw new RouteError(`UNKNOWN_EVIDENCE_SUBCOMMAND: ${JSON.stringify(sub)} is not init, validate or bind`);
}

export async function main(argv: string[]): Promise<number> {
  const args = parseArgs(argv);
  try {
    if (args.command === "handoff") return commandHandoff(args);
    if (args.command === "evidence") return await commandEvidence(args);
    if (args.command === "scan") return commandScan(args);
    if (args.command === "translate") return await commandTranslate(args);
    if (args.command === "repository") return await commandRepository(args);
    console.error(USAGE);
    return args.command === "" || args.command === "--help" ? 0 : 2;
  } catch (error) {
    if (error instanceof RouteError) {
      console.log(JSON.stringify({ status: "BLOCKED", reason: error.message }, null, 2));
      return 2;
    }
    throw error;
  }
}

if (require.main === module) {
  main(process.argv.slice(2)).then((code) => { process.exitCode = code; });
}

export type { Framework };
