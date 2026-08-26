/**
 * Coverage pre-check: answer "how much of this repository can this engine
 * actually convert?" BEFORE anyone commits to a migration.
 *
 * Why this exists. A certified subset is only honest if its boundary is
 * visible in advance. Without a pre-check the only way to find out that a
 * repository is 12% convertible is to run the whole conversion and read
 * the wreckage in `coverage-report.json`. That is a bad way to learn it,
 * and it is the moment a customer concludes the tool was oversold.
 *
 * What this is:
 *
 *   - **Parse-only.** Every discovered component is run through its real
 *     framework parser. Nothing is emitted, nothing is written, no target
 *     project is scaffolded. It is fast enough to run on a repository you
 *     have not decided to migrate.
 *
 *   - **Counted, never extrapolated.** Every number is a count of files
 *     actually parsed. There is no sampling, no estimate, no "typically
 *     around 70%".
 *
 *   - **An UPPER BOUND, and it says so.** Parsing proves a component is
 *     inside `certified-component-v1` from the SOURCE side. Emission is
 *     still re-validated by the target's real compiler during a real run,
 *     and a component can fail there. So `inSubset` is the ceiling on what
 *     any given target will convert, not a promise. `runRepository` is
 *     what produces the verified number.
 *
 *   - **Blockers ranked by frequency**, because the actionable question is
 *     never "which 400 files failed" but "which three constructs would
 *     unlock most of them".
 *
 * An engine defect is NOT a subset boundary. If a parser throws something
 * other than DialectError, that file is counted as SCAN_ERROR and reported
 * separately, so a crash can never be laundered into "out of subset".
 */
import * as fs from "fs";
import * as path from "path";
import { DialectError, Framework, RouteError, isParseable } from "./models";
import { parseComponentResults } from "./engine";
import { discoverComponents } from "./pipeline";
import { MiniProgramSource } from "./parsers/miniprogram";
import { createReactProjectContext, ReactParserOptions } from "./parsers/react";

export type BlockerFamily =
  | "props-and-types"
  | "state"
  | "structure"
  | "expressions"
  | "event-handlers"
  | "list-rendering"
  | "elements-and-attributes"
  | "not-a-single-component"
  | "source-format";

/** Plain-language meaning per reason code, plus the family it belongs to.
 *
 * This table is the difference between a report a customer can act on and
 * a wall of SCREAMING_SNAKE_CASE. Codes absent here fall back to the raw
 * message, which is always populated -- an unmapped code degrades to less
 * readable, never to wrong. */
const BLOCKER_CATALOG: Record<string, { family: BlockerFamily; what: string }> = {
  CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT: { family: "structure", what: "a statement other than useState/return in the component body -- most often an effect hook, a derived const, or a helper function" },
  CERTIFIED_COMPONENT_UNSUPPORTED_PROP_TYPE: { family: "props-and-types", what: "a prop whose type is outside string/number/boolean, a list of those, or an on*-callback" },
  CERTIFIED_COMPONENT_UNSUPPORTED_PROPS_TYPE: { family: "props-and-types", what: "props declared by a named type or interface rather than an inline object literal" },
  CERTIFIED_COMPONENT_UNSUPPORTED_TYPE: { family: "props-and-types", what: "a type annotation outside the certified primitive set" },
  CERTIFIED_COMPONENT_MISSING_TYPE: { family: "props-and-types", what: "an untyped prop or state value -- the canonical model needs a declared type to emit for every target" },
  CERTIFIED_COMPONENT_UNSUPPORTED_PARAMS: { family: "props-and-types", what: "a component signature that is not a single inline-destructured props object" },
  CERTIFIED_COMPONENT_BAD_CALLBACK_NAME: { family: "props-and-types", what: "a callback prop not named on* -- the name is what maps to each target's event convention" },
  CERTIFIED_COMPONENT_TOO_MANY_CALLBACK_ARGS: { family: "props-and-types", what: "a callback prop taking more than one argument" },
  CERTIFIED_COMPONENT_UNSUPPORTED_CALLBACK_ARITY: { family: "props-and-types", what: "a callback prop whose arity has no equivalent on every target" },
  CERTIFIED_COMPONENT_DUPLICATE_PROP: { family: "props-and-types", what: "the same prop declared twice" },
  CERTIFIED_COMPONENT_UNSUPPORTED_EMITS_TYPE: { family: "props-and-types", what: "a Vue emits declaration outside the certified shape" },

  CERTIFIED_COMPONENT_STATE_TYPE_MISMATCH: { family: "state", what: "useState whose declared type and initial literal disagree" },
  CERTIFIED_COMPONENT_DUPLICATE_STATE: { family: "state", what: "the same state variable declared twice" },
  CERTIFIED_COMPONENT_NONSTANDARD_SETTER_NAME: { family: "state", what: "a useState setter not named setX -- targets derive the mutation site from that name" },
  CERTIFIED_COMPONENT_BAD_SETSTATE_ARITY: { family: "state", what: "a setter called with something other than one value (e.g. the updater-function form)" },

  CERTIFIED_COMPONENT_MULTIPLE_ROOTS: { family: "structure", what: "more than one root element -- fragments have no equivalent in several targets" },
  CERTIFIED_COMPONENT_MULTI_LEVEL_CONDITIONAL: { family: "structure", what: "nested or chained conditionals; only one flat conditional is certified" },
  CERTIFIED_COMPONENT_MISSING_RETURN: { family: "structure", what: "no return of JSX/template" },
  CERTIFIED_COMPONENT_MISSING_BODY: { family: "structure", what: "an empty component body" },
  CERTIFIED_COMPONENT_UNSUPPORTED_JSX_CHILD: { family: "structure", what: "a child node kind outside element/text/interpolation/conditional/list -- commonly children, slots, or a rendered component reference" },
  CERTIFIED_COMPONENT_UNSUPPORTED_JSX_NODE: { family: "structure", what: "a JSX node kind outside the certified set (fragments, spreads, embedded components)" },
  CERTIFIED_COMPONENT_UNSUPPORTED_TEMPLATE_NODE: { family: "structure", what: "a template node kind outside the certified set" },
  CERTIFIED_COMPONENT_EMPTY_JSX_EXPRESSION: { family: "structure", what: "an empty `{}` expression slot" },
  CERTIFIED_COMPONENT_UNSUPPORTED_SFC: { family: "structure", what: "a single-file component shape outside the certified one (multiple blocks, unsupported lang, etc.)" },

  CERTIFIED_COMPONENT_UNSUPPORTED_EXPRESSION: { family: "expressions", what: "an expression outside identifiers, literals, ! && || + - * / %, comparisons and ternaries -- function calls are the usual cause" },
  CERTIFIED_COMPONENT_UNSUPPORTED_OPERATOR: { family: "expressions", what: "an operator outside the certified set" },
  CERTIFIED_COMPONENT_UNSUPPORTED_MEMBER_ACCESS: { family: "expressions", what: "member access on something other than a list item (e.g. `props.a.b`, computed subscripts)" },
  CERTIFIED_COMPONENT_UNSUPPORTED_LITERAL: { family: "expressions", what: "a literal outside string/number/boolean" },
  CERTIFIED_COMPONENT_UNKNOWN_IDENTIFIER: { family: "expressions", what: "an identifier that is neither a prop, state, nor the bound list item -- typically an import or module-scope constant" },
  CERTIFIED_COMPONENT_UNSUPPORTED_IDENTIFIER: { family: "expressions", what: "an identifier form outside the certified set" },
  CERTIFIED_COMPONENT_UNKNOWN_PROP: { family: "expressions", what: "a reference to a prop that was never declared" },
  CERTIFIED_COMPONENT_OBJECT_PROP_READ: { family: "expressions", what: "a structured object/array prop rendered as a bare value, which would stringify differently across targets" },
  CERTIFIED_COMPONENT_EXPRESSION_PARSE_FAILED: { family: "expressions", what: "an expression the real parser could not read as a certified expression" },

  CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_STATEMENT: { family: "event-handlers", what: "a handler statement outside state assignment and callback invocation -- loops, conditionals, async and arbitrary calls are excluded" },
  CERTIFIED_COMPONENT_UNSUPPORTED_HANDLER_CALL: { family: "event-handlers", what: "a handler calling something other than a setter or a declared callback prop" },
  CERTIFIED_COMPONENT_UNKNOWN_HANDLER: { family: "event-handlers", what: "an event bound to a handler that is not defined inline" },
  CERTIFIED_COMPONENT_UNKNOWN_CALLBACK_TARGET: { family: "event-handlers", what: "a call to an undeclared callback" },
  CERTIFIED_COMPONENT_UNKNOWN_STATE_TARGET: { family: "event-handlers", what: "an assignment to something that is not declared state" },
  CERTIFIED_COMPONENT_UNKNOWN_EMITTED_EVENT: { family: "event-handlers", what: "an emitted event that was never declared" },
  CERTIFIED_COMPONENT_HANDLER_PARSE_FAILED: { family: "event-handlers", what: "a handler body the real parser could not read as a certified handler" },
  CERTIFIED_COMPONENT_BAD_EVENT_BINDING: { family: "event-handlers", what: "an event binding shape outside the certified one" },
  CERTIFIED_COMPONENT_UNSUPPORTED_EVENT: { family: "event-handlers", what: "an event outside onClick/onChange/onInput/onSubmit" },

  CERTIFIED_COMPONENT_UNSUPPORTED_LIST_SOURCE: { family: "list-rendering", what: "iterating an expression rather than a declared list prop" },
  CERTIFIED_COMPONENT_UNKNOWN_LIST_SOURCE: { family: "list-rendering", what: "iterating something that is not a declared list prop" },
  CERTIFIED_COMPONENT_UNSUPPORTED_LIST_CALLBACK: { family: "list-rendering", what: "a .map callback that is not a single plain item parameter with an expression body -- index parameters and destructuring are excluded because they change list identity per target" },
  CERTIFIED_COMPONENT_UNSUPPORTED_LIST_BODY: { family: "list-rendering", what: "a list body that is not exactly one element node" },
  CERTIFIED_COMPONENT_UNSUPPORTED_LIST_ELEMENT: { family: "list-rendering", what: "a list element type outside a primitive or a bounded object shape (array fields remain blocked)" },
  CERTIFIED_COMPONENT_MISSING_LIST_KEY: { family: "list-rendering", what: "object list items with no identity field (`id`, or exactly one *Id/*Key) -- no target can be given a correct key, and an index key is the defect this engine exists to prevent" },
  CERTIFIED_COMPONENT_UNKNOWN_LIST_KEY: { family: "list-rendering", what: "a declared list key that is not a field of the element" },
  CERTIFIED_COMPONENT_UNEXPECTED_LIST_KEY: { family: "list-rendering", what: "a key on a primitive list, which is keyed by its own value" },
  CERTIFIED_COMPONENT_UNKNOWN_LIST_FIELD: { family: "list-rendering", what: "reading a field that is not declared on the list element type" },
  CERTIFIED_COMPONENT_OBJECT_ITEM_READ: { family: "list-rendering", what: "rendering an object list item directly instead of one of its fields" },
  CERTIFIED_COMPONENT_NESTED_LIST: { family: "list-rendering", what: "a list inside a list" },
  CERTIFIED_COMPONENT_LIST_ITEM_SHADOWS: { family: "list-rendering", what: "a list item name that shadows a prop or state variable" },
  CERTIFIED_COMPONENT_EMPTY_LIST_ELEMENT: { family: "list-rendering", what: "an object list element with no fields" },
  CERTIFIED_COMPONENT_UNSUPPORTED_LIST_DEFAULT: { family: "list-rendering", what: "a default value on a list prop" },
  CERTIFIED_COMPONENT_UNRECOVERABLE_LIST_ELEMENT: { family: "list-rendering", what: "a Vue 2 / WeChat list prop declared only as `Array`, with no element type -- both can be list TARGETS but not list SOURCES, because recovering the element shape would mean guessing field types" },

  CERTIFIED_COMPONENT_UNSUPPORTED_TAG: { family: "elements-and-attributes", what: "an element outside div/span/p/button/input/label/a/h1-h6/ul/li/strong/em" },
  CERTIFIED_COMPONENT_UNSUPPORTED_ATTRIBUTE: { family: "elements-and-attributes", what: "an attribute outside class/id/href/type/placeholder/value/disabled/name/for/checked -- inline style and data-* are the usual causes" },
  CERTIFIED_COMPONENT_UNSUPPORTED_DIRECTIVE: { family: "elements-and-attributes", what: "a framework directive outside v-if/v-else/v-for and their equivalents" },

  CERTIFIED_COMPONENT_EXPECTED_ONE_FUNCTION: { family: "not-a-single-component", what: "the file declares no component at all -- a barrel/index re-export or a non-component module" },
  CERTIFIED_COMPONENT_DUPLICATE_COMPONENT: { family: "not-a-single-component", what: "two components in one file share a name" },
  CERTIFIED_COMPONENT_NOT_A_COMPONENT: { family: "not-a-single-component", what: "a function that returns no JSX -- a helper, not a component" },
  CERTIFIED_COMPONENT_SELF_REFERENCE: { family: "structure", what: "a component that renders itself; recursion has no termination proof in this profile" },
  CERTIFIED_COMPONENT_UNSUPPORTED_SLOT: { family: "structure", what: "slot / children projection into a child component -- each target evaluates it differently (children, <slot>, <ng-content>, @BuilderParam)" },
  CERTIFIED_COMPONENT_MISSING_NAME: { family: "not-a-single-component", what: "an anonymous or default-exported-inline component" },
  CERTIFIED_COMPONENT_BAD_NAME: { family: "not-a-single-component", what: "a name that is not a PascalCase identifier" },

  CERTIFIED_COMPONENT_PARSE_FAILED: { family: "source-format", what: "the framework's own compiler rejected the file -- a syntax error, or a dialect the installed compiler does not accept" },
  CERTIFIED_COMPONENT_MISSING_SCRIPT: { family: "source-format", what: "a WeChat .wxml with no sibling .js -- a mini program component is a file pair, and half of it is missing" },
};

export type FindingStatus =
  | "IN_SUBSET"
  | "OUT_OF_SUBSET"
  /**
   * A function that returns no JSX -- a helper living beside the
   * components in the same file. Excluded from the coverage denominator
   * because it is not a migration unit at all: counting it as a failed
   * component would understate coverage AND fill the blocker ranking with
   * reasons no subset widening could ever fix. Still listed, so the
   * exclusion is visible rather than silent.
   */
  | "NOT_A_COMPONENT"
  | "SCAN_ERROR";

export interface ScanFinding {
  sourcePath: string;
  /** The declared component name, when the parser got far enough to read
   * one. A file can declare several. */
  componentName: string | null;
  status: FindingStatus;
  reasonCode: string | null;
  reason: string | null;
  family: BlockerFamily | null;
}

export interface BlockerGroup {
  reasonCode: string;
  family: BlockerFamily | null;
  what: string;
  count: number;
  /** Share of out-of-subset components, rounded to 3 decimals. */
  shareOfBlocked: number;
  /** Capped sample; `count` is the true total. */
  exampleFiles: string[];
}

export interface FamilyGroup {
  family: BlockerFamily;
  count: number;
  shareOfBlocked: number;
}

export interface FeasibilityReport {
  schemaVersion: "1.0";
  kind: "elmos.component-dialect-feasibility-scan";
  profile: "certified-component-v1";
  repository: string;
  sourceFramework: Framework;
  scannedAt: string;
  totals: {
    /** COMPONENTS, not files -- one file can declare several. */
    discovered: number;
    inSubset: number;
    outOfSubset: number;
    /** Engine failures, NOT subset boundaries. Any value above 0 is a bug
     * in this engine and is reported as such rather than folded into
     * outOfSubset. */
    scanErrors: number;
    /** Helper functions found beside the components. Excluded from
     * `discovered` and from the coverage ratio; reported so the exclusion
     * is auditable. */
    notComponents: number;
  };
  /** inSubset / discovered, rounded to 3 decimals. An UPPER BOUND on what
   * a real run will convert -- see `caveats`. */
  upperBoundCoverage: number;
  blockers: BlockerGroup[];
  families: FamilyGroup[];
  findings: ScanFinding[];
  caveats: string[];
}

export interface ScanOptions {
  repository: string;
  sourceFramework: Framework;
  /** Cap on example files listed per blocker. The count is always exact. */
  examplesPerBlocker?: number;
  /** Emit every finding, not just blocked ones. Off by default so the
   * report stays readable on large repositories. */
  includeAllFindings?: boolean;
}

function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

/**
 * Parse every discovered component and report subset membership.
 *
 * Writes nothing. Emits nothing. Needs no target framework -- membership
 * is a property of the source, which is exactly why this can be answered
 * before anyone picks a migration target.
 */
export function scanRepository(options: ScanOptions): FeasibilityReport {
  const { repository, sourceFramework } = options;
  const examplesPerBlocker = options.examplesPerBlocker ?? 5;

  if (!fs.existsSync(repository)) {
    throw new RouteError(`REPOSITORY_NOT_FOUND: ${repository}`);
  }
  if (!isParseable(sourceFramework)) {
    throw new RouteError(
      `FRAMEWORK_NOT_PARSEABLE: ${sourceFramework} can only be a translation TARGET, so a repository ` +
      `written in it cannot be scanned. See README for why ArkUI and Flutter are emit-only.`,
    );
  }

  const files = discoverComponents(repository, sourceFramework);
  const reactProject = sourceFramework === "react" || sourceFramework === "typescript" || sourceFramework === "react-native"
    ? createReactProjectContext(repository)
    : undefined;
  const findings: ScanFinding[] = [];

  for (const file of files) {
    const relative = path.relative(repository, file);
    let source: string | MiniProgramSource;
    try {
      if (sourceFramework === "miniprogram") {
        // A mini program component is a .wxml + .js pair. Scanning only the
        // template would mis-report every mini program repository.
        const jsFile = file.replace(/\.wxml$/, ".js");
        if (!fs.existsSync(jsFile)) {
          findings.push({
            sourcePath: relative, componentName: null, status: "OUT_OF_SUBSET",
            reasonCode: "CERTIFIED_COMPONENT_MISSING_SCRIPT",
            reason: `no sibling ${path.basename(jsFile)} was found next to ${path.basename(file)}`,
            family: "source-format",
          });
          continue;
        }
        source = { wxml: fs.readFileSync(file, "utf8"), js: fs.readFileSync(jsFile, "utf8") };
      } else {
        source = fs.readFileSync(file, "utf8");
      }
    } catch (error) {
      findings.push({
        sourcePath: relative, componentName: null, status: "SCAN_ERROR", reasonCode: "FILE_UNREADABLE",
        reason: error instanceof Error ? error.message : String(error), family: null,
      });
      continue;
    }

    // Counted per COMPONENT, not per file, because that is what the
    // pipeline emits: a file declaring five components produces five
    // outcomes, and one of them being blocked no longer costs the other
    // four.
    try {
      const reactOptions: ReactParserOptions = reactProject === undefined ? {} : {
        project: reactProject,
        sourceFile: reactProject.program.getSourceFile(path.resolve(file)),
      };
      for (const result of parseComponentResults(source, sourceFramework, path.basename(file), reactOptions)) {
        if (result.component !== null) {
          findings.push({ sourcePath: relative, componentName: result.component.name, status: "IN_SUBSET", reasonCode: null, reason: null, family: null });
        } else {
          const code = result.error?.code ?? "UNKNOWN";
          findings.push({
            sourcePath: relative, componentName: result.name,
            status: code === "CERTIFIED_COMPONENT_NOT_A_COMPONENT" ? "NOT_A_COMPONENT" : "OUT_OF_SUBSET",
            reasonCode: code, reason: result.error?.reason ?? null,
            family: BLOCKER_CATALOG[code]?.family ?? null,
          });
        }
      }
    } catch (error) {
      if (error instanceof DialectError) {
        findings.push({
          sourcePath: relative, componentName: null, status: "OUT_OF_SUBSET",
          reasonCode: error.code, reason: error.reason,
          family: BLOCKER_CATALOG[error.code]?.family ?? null,
        });
      } else {
        // Not a subset boundary -- an engine defect. Counted separately so
        // it cannot be laundered into a coverage number.
        findings.push({
          sourcePath: relative, componentName: null, status: "SCAN_ERROR", reasonCode: "ENGINE_ERROR",
          reason: error instanceof Error ? error.message : String(error), family: null,
        });
      }
    }
  }

  const inSubset = findings.filter((f) => f.status === "IN_SUBSET").length;
  const blocked = findings.filter((f) => f.status === "OUT_OF_SUBSET");
  const scanErrors = findings.filter((f) => f.status === "SCAN_ERROR").length;
  const notComponents = findings.filter((f) => f.status === "NOT_A_COMPONENT").length;
  const denominator = inSubset + blocked.length;

  const byCode = new Map<string, ScanFinding[]>();
  for (const finding of blocked) {
    const code = finding.reasonCode ?? "UNKNOWN";
    const bucket = byCode.get(code);
    if (bucket) bucket.push(finding);
    else byCode.set(code, [finding]);
  }

  const blockers: BlockerGroup[] = [...byCode.entries()]
    .map(([reasonCode, group]) => ({
      reasonCode,
      family: BLOCKER_CATALOG[reasonCode]?.family ?? null,
      what: BLOCKER_CATALOG[reasonCode]?.what ?? (group[0]?.reason ?? "no description available"),
      count: group.length,
      shareOfBlocked: blocked.length === 0 ? 0 : round3(group.length / blocked.length),
      exampleFiles: group.slice(0, examplesPerBlocker).map((f) => f.sourcePath),
    }))
    // Frequency first; ties broken by code so the report is deterministic
    // and diffable across runs.
    .sort((a, b) => b.count - a.count || a.reasonCode.localeCompare(b.reasonCode));

  const byFamily = new Map<BlockerFamily, number>();
  for (const finding of blocked) {
    if (finding.family === null) continue;
    byFamily.set(finding.family, (byFamily.get(finding.family) ?? 0) + 1);
  }
  const families: FamilyGroup[] = [...byFamily.entries()]
    .map(([family, count]) => ({ family, count, shareOfBlocked: blocked.length === 0 ? 0 : round3(count / blocked.length) }))
    .sort((a, b) => b.count - a.count || a.family.localeCompare(b.family));

  const caveats = [
    "This is an UPPER BOUND. Parsing proves a component is inside certified-component-v1 from the SOURCE side. " +
    "During a real run each emission is re-validated by the target framework's own compiler, and a component can " +
    "still be reported BLOCKED there. Run `repository` to get the verified number for a specific target.",
    "Counts are exact -- every discovered file was really parsed by its framework's real compiler. Nothing here " +
    "is sampled or extrapolated.",
    "TypeScript's parser is deliberately error-tolerant: it builds a tree from broken input rather than throwing. " +
    "A malformed .tsx can therefore be classified by whichever check fires first -- including as a helper -- rather " +
    "than surfacing as a syntax error. Vue, Svelte and Angular sources do not share this behavior; their compilers reject.",
    "The denominator counts COMPONENTS, not files -- one file can declare several, and each is judged on its own. " +
    "Functions that return no JSX are helpers, not migration units: they are excluded from the ratio and reported " +
    "under `notComponents` so the exclusion is auditable rather than silent. Everything that IS a component stays " +
    "in the denominator, including ones blocked for reasons no widening will fix.",
  ];
  if (scanErrors > 0) {
    caveats.unshift(
      `${scanErrors} file(s) produced SCAN_ERROR. Those are engine defects or unreadable files, NOT subset ` +
      "boundaries, and they are excluded from the blocker ranking. Please report them.",
    );
  }

  return {
    schemaVersion: "1.0",
    kind: "elmos.component-dialect-feasibility-scan",
    profile: "certified-component-v1",
    repository: path.resolve(repository),
    sourceFramework,
    scannedAt: new Date().toISOString(),
    totals: { discovered: denominator, inSubset, outOfSubset: blocked.length, scanErrors, notComponents },
    upperBoundCoverage: denominator === 0 ? 0 : round3(inSubset / denominator),
    blockers,
    families,
      findings: options.includeAllFindings ? findings : findings.filter((f) => f.status !== "IN_SUBSET"),
    caveats,
  };
}

/**
 * Human-readable rendering of the same facts.
 *
 * A migration decision gets made by someone who will not read JSON, and if
 * the honest version is only available as JSON the optimistic version is
 * what reaches the decision.
 */
export function renderFeasibilityMarkdown(report: FeasibilityReport): string {
  const { totals } = report;
  const percent = (value: number): string => `${(value * 100).toFixed(1)}%`;
  const lines: string[] = [
    `# Feasibility scan -- ${report.profile}`,
    "",
    `- Repository: \`${report.repository}\``,
    `- Source framework: \`${report.sourceFramework}\``,
    `- Scanned: ${report.scannedAt}`,
    "",
    "## Result",
    "",
    `**${totals.inSubset} of ${totals.discovered} discovered components are inside the certified subset ` +
    `(${percent(report.upperBoundCoverage)}, upper bound).**`,
    "",
    `| | Count |`,
    `|---|---|`,
    `| Discovered components | ${totals.discovered} |`,
    `| In subset (upper bound) | ${totals.inSubset} |`,
    `| Out of subset | ${totals.outOfSubset} |`,
    `| Helper functions (not components, excluded) | ${totals.notComponents} |`,
    `| Scan errors (engine defects) | ${totals.scanErrors} |`,
    "",
  ];

  if (report.blockers.length > 0) {
    lines.push("## What is blocking, most frequent first", "");
    lines.push("| Blocker | Files | Share | What it is |", "|---|---|---|---|");
    for (const blocker of report.blockers) {
      lines.push(`| \`${blocker.reasonCode}\` | ${blocker.count} | ${percent(blocker.shareOfBlocked)} | ${blocker.what} |`);
    }
    lines.push("");
    lines.push("### By family", "");
    lines.push("| Family | Files | Share |", "|---|---|---|");
    for (const family of report.families) {
      lines.push(`| ${family.family} | ${family.count} | ${percent(family.shareOfBlocked)} |`);
    }
    lines.push("");
    const top = report.blockers[0];
    if (top && report.blockers.length > 1) {
      lines.push(
        `Removing the single largest blocker (\`${top.reasonCode}\`) would move at most ${top.count} ` +
        `component(s) -- "at most" because a file can be blocked by more than one construct and only the ` +
        `first one encountered is reported here.`,
        "",
      );
    }
  }

  lines.push("## Read this before deciding", "");
  for (const caveat of report.caveats) lines.push(`- ${caveat}`);
  lines.push("");
  return lines.join("\n");
}
