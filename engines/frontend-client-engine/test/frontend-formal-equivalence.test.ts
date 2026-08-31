import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  buildFrontendSmt2,
  canonicalBoundedNavigationModel,
  frontendFormalDigest,
  frontendFormalFixtureRequest,
  lockedZ3BinaryDigestFor,
  materializeFrontendFormalCampaign,
  observeBoundedNavigationModel,
  reliftBoundedNavigationProject,
  runFrontendSolver,
  verifyFrontendFormalCampaign,
} from "../src/frontend-formal-equivalence.js";
import { generateUiProject } from "../src/project-generation.js";
import { uiConversionRoutes, uiTargetProfiles } from "../src/project-profiles.js";
import { navigationSourceSpec, type BoundedNavigationSemanticModel } from "../src/bounded-navigation-source.js";

function sha256Bytes(value: string): string {
  return `sha256:${createHash("sha256").update(value, "utf8").digest("hex")}`;
}

test("locked Z3 artifacts are exact per supported platform tuple", () => {
  assert.equal(
    lockedZ3BinaryDigestFor("darwin", "arm64"),
    "sha256:537a502af2f4013a8e887beebe525a0dae84918a61ff545991e36dfda07ed6d7",
  );
  assert.equal(
    lockedZ3BinaryDigestFor("linux", "x64"),
    "sha256:e583c4186a45e72411fa2cb2048401eed03f0f8e5f24694676a8f6271a50b765",
  );
  assert.equal(lockedZ3BinaryDigestFor("win32", "x64"), null);
  assert.equal(lockedZ3BinaryDigestFor("linux", "arm64"), null);
});

function matchingBrace(text: string, open: number): number {
  let depth = 0;
  let quote: "'" | '"' | "`" | null = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let index = open; index < text.length; index += 1) {
    const current = text[index]!;
    const next = text[index + 1];
    if (lineComment) {
      if (current === "\n") lineComment = false;
      continue;
    }
    if (blockComment) {
      if (current === "*" && next === "/") { blockComment = false; index += 1; }
      continue;
    }
    if (quote !== null) {
      if (escaped) escaped = false;
      else if (current === "\\") escaped = true;
      else if (current === quote) quote = null;
      continue;
    }
    if (current === "/" && next === "/") { lineComment = true; index += 1; continue; }
    if (current === "/" && next === "*") { blockComment = true; index += 1; continue; }
    if (current === "'" || current === '"' || current === "`") { quote = current; continue; }
    if (current === "{") depth += 1;
    if (current === "}" && --depth === 0) return index;
  }
  throw new Error("test mutation could not match a consumer body");
}

function replaceConsumerBody(
  source: string,
  marker: string,
  replacement: (originalBody: string) => string,
): string {
  const markerAt = source.indexOf(marker);
  assert.notEqual(markerAt, -1, `consumer marker missing: ${marker}`);
  const open = source.indexOf("{", markerAt + marker.length);
  assert.notEqual(open, -1, `consumer body missing: ${marker}`);
  const close = matchingBrace(source, open);
  return `${source.slice(0, open + 1)}${replacement(source.slice(open + 1, close))}${source.slice(close)}`;
}

function replaceSfcTemplateWithStatic(source: string): string {
  const match = /<template>[\s\S]*?<\/template>/.exec(source);
  assert.ok(match, "Vue template mutation target is missing");
  const withUnused = source.replace("</script>", `const UNUSED_CONSUMER = \`${match[0]}\`;\n</script>`);
  return withUnused.replace(match[0], "<template><main>STATIC</main></template>");
}

function replaceSvelteMarkupWithStatic(source: string): string {
  const scriptEnd = source.indexOf("</script>");
  assert.notEqual(scriptEnd, -1, "Svelte script mutation target is missing");
  const markup = source.slice(scriptEnd + "</script>".length);
  const script = source.slice(0, scriptEnd);
  return `${script}const UNUSED_CONSUMER = \`${markup}\`;\nif (false) { void UNUSED_CONSUMER; }\n</script>\n<div>STATIC</div>\n`;
}

function insertUnusedConsumer(profile: string, source: string): string {
  if (profile === "vue2" || profile === "vue3" || profile === "svelte") {
    return source.replace("</script>", 'const UNUSED_CONSUMER = "route.id route.path route.title";\n</script>');
  }
  if (profile === "flutter") return `${source}\nconst String elmosUnusedConsumer = 'route.id route.path route.title';\n`;
  if (profile === "harmony-arkui") return `${source}\nconst ELMOS_UNUSED_CONSUMER: string = 'item.id item.path item.title';\n`;
  return `${source}\nconst UNUSED_CONSUMER = "route.id route.path route.title";\n`;
}

function insertDeadConsumer(profile: string, source: string): string {
  if (profile === "vue2" || profile === "vue3" || profile === "svelte") {
    return source.replace("</script>", "if (1 === 0) { void routes; }\n</script>");
  }
  if (profile === "flutter") return `${source}\nvoid elmosDeadConsumer() { if (1 == 0) {} }\n`;
  if (profile === "harmony-arkui") return `${source}\nfunction elmosDeadConsumer(): void { if (1 === 0) {} }\n`;
  return `${source}\nif (1 === 0) { void 0; }\n`;
}

test("all nine emitted profile projects re-lift from executable source to one canonical bounded model", () => {
  const digests = new Set<string>();
  for (const profile of uiTargetProfiles()) {
    const request = frontendFormalFixtureRequest(profile.id);
    const project = generateUiProject(request);
    const relift = reliftBoundedNavigationProject(profile.id, project.files);
    const canonical = canonicalBoundedNavigationModel(request);
    assert.deepEqual(relift.model, canonical, profile.id);
    assert.equal(relift.model_digest, frontendFormalDigest(canonical), profile.id);
    assert.equal(relift.consumer_binding.route_table_is_unique, true);
    assert.equal(relift.consumer_binding.fallback_consumer, true);
    assert.equal(Object.keys(relift.spans).length, 33, profile.id);
    digests.add(relift.model_digest);
  }
  assert.equal(digests.size, 1);
});

test("directed bounded-navigation closure is exactly nine profiles and 72 non-self pairs", () => {
  const profiles = uiTargetProfiles();
  const routes = uiConversionRoutes();
  assert.equal(profiles.length, 9);
  assert.equal(routes.length, 72);
  assert.equal(new Set(routes.map(route => `${route.source}->${route.target}`)).size, 72);
  assert.ok(routes.every(route => route.routeId === `${route.source}--to--${route.target}`));
  assert.ok(routes.every(route => route.source !== route.target));
});

test("re-lift rejects renderer tamper, comment decoys, duplicate route tables, and proof-only drift", () => {
  const request = frontendFormalFixtureRequest("react");
  const project = generateUiProject(request);

  const rendererTamper = { ...project.files, "src/App.tsx": project.files["src/App.tsx"]!.replaceAll("routes.map", "[].map") };
  assert.throws(() => reliftBoundedNavigationProject("react", rendererTamper), /consumer AST call binding drifted/);

  const commentDecoy = {
    ...project.files,
    "src/App.tsx": [
      "/* routes.map route.id route.path route.title route.text route.requiresAuth route.deepLink aria-label path=\"*\" routes[0] */",
      "export function App() { return null; }",
    ].join("\n"),
  };
  assert.throws(() => reliftBoundedNavigationProject("react", commentDecoy), /consumer AST/);

  const jquery = generateUiProject(frontendFormalFixtureRequest("jquery"));
  const deadRender = {
    ...jquery.files,
    "src/main.ts": jquery.files["src/main.ts"]!.replace("\nrender(window.location.pathname);\n", "\nvoid 0;\n"),
  };
  assert.throws(() => reliftBoundedNavigationProject("jquery", deadRender), /top-level entry expression/);

  const duplicate = {
    ...project.files,
    "src/App.tsx": `${project.files["src/App.tsx"]}\nconst forbidden = { id: "x", path: "/x", title: "x", text: "x", requiresAuth: false, deepLink: false };\n`,
  };
  assert.throws(() => reliftBoundedNavigationProject("react", duplicate), /duplicate literal route table/);

  const contractPath = "src/elmos-bounded-navigation.ts";
  const proofDrift = { ...project.files, [contractPath]: project.files[contractPath]!.replace('"headingLevel": 1', '"headingLevel": 2') };
  assert.throws(() => reliftBoundedNavigationProject("react", proofDrift), /render contract drifted/);

  const semanticDrift = { ...project.files, [contractPath]: project.files[contractPath]!.replace("首页内容", "篡改首页内容") };
  const drifted = reliftBoundedNavigationProject("react", semanticDrift);
  assert.notEqual(drifted.model_digest, frontendFormalDigest(canonicalBoundedNavigationModel(request)));
});

test("all nine profiles reject static, dead, or unused-string entry replacements", () => {
  const deadNeedles: Record<string, string> = {
    angular: "bootstrapApplication(AppComponent, { providers: [provideRouter(routes)] }).catch(error => console.error(error));",
    jquery: "render(window.location.pathname);",
    react: "createRoot(root).render(<StrictMode><BrowserRouter><App /></BrowserRouter></StrictMode>);",
    "react-native": "registerRootComponent(App);",
    svelte: "mount(App, { target });",
    vue2: 'new Vue({ router, render: create => create(App) }).$mount("#app");',
    vue3: 'createApp(App).use(createPinia()).use(router).mount("#app");',
  };
  for (const profile of uiTargetProfiles()) {
    const project = generateUiProject(frontendFormalFixtureRequest(profile.id));
    const entryPath = navigationSourceSpec(profile.id).entryPath;
    const original = project.files[entryPath]!;
    const staticEntry = profile.id === "flutter"
      ? "import 'package:flutter/material.dart';\nimport 'elmos_bounded_navigation.dart';\nconst String unused = 'runApp MaterialApp elmosFirstRoute';\nvoid main() {}\n"
      : profile.id === "harmony-arkui"
        ? "const UNUSED = \"@Entry @Component struct Index ELMOS_ROUTES Navigation build\";\n"
        : `const UNUSED_ENTRY = ${JSON.stringify(original)};\nexport const STATIC_ENTRY = UNUSED_ENTRY;\n`;
    assert.throws(
      () => reliftBoundedNavigationProject(profile.id, { ...project.files, [entryPath]: staticEntry }),
      /entry|import|dataflow|top-level|ArkUI|Flutter/i,
      `${profile.id} accepted an unused-string static entry`,
    );
    const needle = deadNeedles[profile.id];
    const deadEntry = profile.id === "flutter"
      ? original.replace("void main() => runApp(const GeneratedApp());", "void main() { if (false) { runApp(const GeneratedApp()); } }")
      : profile.id === "harmony-arkui"
        ? `if (false) {}\n${original}`
        : profile.id === "jquery"
          ? original.replace(`\n${needle!}\n`, `\nif (false) { ${needle!} }\n`)
          : original.replace(needle!, `if (false) { ${needle!} }`);
    assert.throws(
      () => reliftBoundedNavigationProject(profile.id, { ...project.files, [entryPath]: deadEntry }),
      /entry|dataflow|top-level|parse/i,
      `${profile.id} accepted a dead entry consumer`,
    );
  }
});

test("all nine profiles reject static, dead, and unused consumer-body bypasses", () => {
  const consumerPaths: Record<string, string> = {
    angular: "src/app/app.component.ts",
    flutter: "lib/main.dart",
    "harmony-arkui": "entry/src/main/ets/pages/Index.ets",
    jquery: "src/main.ts",
    react: "src/App.tsx",
    "react-native": "src/navigation.tsx",
    svelte: "src/App.svelte",
    vue2: "src/App.vue",
    vue3: "src/App.vue",
  };
  for (const profile of uiTargetProfiles()) {
    const project = generateUiProject(frontendFormalFixtureRequest(profile.id));
    const consumerPath = consumerPaths[profile.id]!;
    const original = project.files[consumerPath]!;
    let staticBypass: string;
    switch (profile.id) {
      case "react":
        staticBypass = replaceConsumerBody(original, "export function App()", body => `\n  if (false) {${body}}\n  return <div>STATIC</div>;\n`);
        break;
      case "react-native":
        staticBypass = replaceConsumerBody(
          original,
          'export function GeneratedNavigation({ requestedPath = "/__elmos_initial__" }: { readonly requestedPath?: string } = {})',
          body => `\n  if (false) {${body}}\n  return <View />;\n`,
        );
        break;
      case "jquery":
        staticBypass = replaceConsumerBody(original, "function render(", body => `\n  if (false) {${body}}\n  document.body.textContent = "STATIC";\n`);
        break;
      case "vue2":
      case "vue3":
        staticBypass = replaceSfcTemplateWithStatic(original);
        break;
      case "svelte":
        staticBypass = replaceSvelteMarkupWithStatic(original);
        break;
      case "angular": {
        const template = /template: `([^`]*)`,/.exec(original);
        assert.ok(template?.[1], "Angular template mutation target is missing");
        staticBypass = `${original.replace(template[0], "template: `<main>STATIC</main>`,")}\nconst UNUSED_CONSUMER = \`${template[1]}\`;\n`;
        break;
      }
      case "flutter":
        staticBypass = replaceConsumerBody(original, "class GeneratedPage extends StatelessWidget", body => {
          const buildAt = body.indexOf("Widget build(BuildContext context)");
          assert.notEqual(buildAt, -1, "Flutter page build mutation target is missing");
          const open = body.indexOf("{", buildAt);
          const close = matchingBrace(body, open);
          const buildBody = body.slice(open + 1, close);
          return `${body.slice(0, open + 1)}\n    if (1 == 0) {${buildBody}}\n    return const SizedBox.shrink();\n  ${body.slice(close)}`;
        });
        break;
      case "harmony-arkui": {
        let originalBody = "";
        staticBypass = replaceConsumerBody(original, "build()", body => {
          originalBody = body;
          return "\n    Navigation() { Text('STATIC') }\n  ";
        });
        staticBypass = `${staticBypass}\nconst UNUSED_CONSUMER: string = \`${originalBody}\`;\n`;
        break;
      }
    }
    for (const [kind, tampered] of [
      ["static", staticBypass],
      ["dead", insertDeadConsumer(profile.id, original)],
      ["unused", insertUnusedConsumer(profile.id, original)],
    ] as const) {
      assert.throws(
        () => reliftBoundedNavigationProject(profile.id, { ...project.files, [consumerPath]: tampered }),
        /reachable generated consumer grammar drifted/,
        `${profile.id} accepted a ${kind} consumer-body bypass`,
      );
    }
  }
});

test("every profile rejects copied, filtered, or sliced route aliases", () => {
  for (const profile of uiTargetProfiles()) {
    const project = generateUiProject(frontendFormalFixtureRequest(profile.id));
    const sourcePath = navigationSourceSpec(profile.id).sourcePath;
    const source = project.files[sourcePath]!;
    const copied = profile.id === "flutter"
      ? source.replace(
        "final List<Object?> elmosBoundedRoutes = elmosBoundedNavigation['routes']! as List<Object?>;",
        "final List<Object?> elmosBoundedRoutes = (elmosBoundedNavigation['routes']! as List<Object?>).sublist(0, 1);",
      )
      : source.replace(
        "export const ELMOS_ROUTES = ELMOS_BOUNDED_NAVIGATION.routes;",
        "export const ELMOS_ROUTES = ELMOS_BOUNDED_NAVIGATION.routes.slice(0, 1);",
      );
    assert.throws(
      () => reliftBoundedNavigationProject(profile.id, { ...project.files, [sourcePath]: copied }),
      /direct.*identity alias/i,
      `${profile.id} accepted a copied route alias`,
    );
  }
  const react = generateUiProject(frontendFormalFixtureRequest("react"));
  assert.throws(() => reliftBoundedNavigationProject("react", {
    ...react.files,
    "src/routes.ts": react.files["src/routes.ts"]!.replace("export const routes = ELMOS_ROUTES;", "export const routes = ELMOS_ROUTES.filter(() => true);"),
  }), /direct identity alias/);
  const ark = generateUiProject(frontendFormalFixtureRequest("harmony-arkui"));
  assert.throws(() => reliftBoundedNavigationProject("harmony-arkui", {
    ...ark.files,
    "entry/src/main/ets/pages/Index.ets": ark.files["entry/src/main/ets/pages/Index.ets"]!.replace("= ELMOS_ROUTES;", "= ELMOS_ROUTES.slice(0, 1);"),
  }), /direct identity alias/);
});

test("six web targets expose selected route metadata on main and route identity on nav links", () => {
  for (const id of ["react", "vue2", "vue3", "jquery", "angular", "svelte"] as const) {
    const files = generateUiProject(frontendFormalFixtureRequest(id)).files;
    const source = Object.entries(files).filter(([path]) => /(?:App|GeneratedPage|generated-page\.component|main|app\.component)\.(?:tsx|ts|js|vue|svelte)$/.test(path)).map(([, value]) => value).join("\n");
    for (const marker of ["data-route-id", "data-route-path", "data-requires-auth", "data-deep-link"]) {
      assert.ok(source.includes(marker), `${id} omitted ${marker}`);
    }
  }
});

test("symbolic SMT proves all input paths only under assumptions and finds semantic, fallback, and behavior counterexamples", () => {
  const canonical = canonicalBoundedNavigationModel(frontendFormalFixtureRequest("react"));
  const observations = observeBoundedNavigationModel(canonical, "canonical");
  const equal = runFrontendSolver(buildFrontendSmt2(canonical, canonical, canonical, observations, observations, observations, observations, "sha256:test"));
  assert.equal(equal.outcome, "UNSAT");
  assert.equal(equal.proof_status, "PROVED_UNDER_ASSUMPTIONS");
  assert.equal(equal.unconditional_proof, false);

  const fieldDrift = structuredClone(canonical) as { routes: Array<{ title: string }> } & BoundedNavigationSemanticModel;
  fieldDrift.routes[1]!.title = "drift";
  const fieldResult = runFrontendSolver(buildFrontendSmt2(canonical, canonical, fieldDrift, observations, observations, observations, observeBoundedNavigationModel(fieldDrift, "target"), "sha256:test"));
  assert.equal(fieldResult.outcome, "SAT");
  assert.equal(fieldResult.proof_status, "REFUTED");

  const fallbackDrift = structuredClone(canonical) as { routes: BoundedNavigationSemanticModel["routes"][number][] } & BoundedNavigationSemanticModel;
  fallbackDrift.routes = [fallbackDrift.routes[1]!, fallbackDrift.routes[0]!, fallbackDrift.routes[2]!];
  const fallbackResult = runFrontendSolver(buildFrontendSmt2(canonical, canonical, fallbackDrift, observations, observations, observations, observeBoundedNavigationModel(fallbackDrift, "target"), "sha256:test"));
  assert.equal(fallbackResult.outcome, "SAT");

  const behaviorDrift = structuredClone(observations) as Array<(typeof observations)[number]>;
  behaviorDrift[1] = { ...behaviorDrift[1]!, route: { ...behaviorDrift[1]!.route, text: "behavior drift" } };
  const behaviorResult = runFrontendSolver(buildFrontendSmt2(canonical, canonical, canonical, observations, observations, observations, behaviorDrift, "sha256:test"));
  assert.equal(behaviorResult.outcome, "SAT");
});

test("solver identity, unknown, nonzero, and strict stdout checks fail closed", () => {
  const missing = runFrontendSolver("(check-sat)\n", { command: "/definitely/missing/elmos-z3" });
  assert.equal(missing.outcome, "MISSING");
  assert.equal(missing.proof_status, "NOT_PROVED");

  const root = mkdtempSync(join(tmpdir(), "elmos-fake-z3-"));
  const fake = join(root, "z3");
  writeFileSync(fake, "#!/bin/sh\nif [ \"$1\" = \"-version\" ]; then echo 'Z3 version 4.16.0 - 64 bit'; else echo unsat; fi\n", "utf8");
  chmodSync(fake, 0o755);
  const fakeResult = runFrontendSolver("(check-sat)\n", { command: fake });
  assert.equal(fakeResult.identity_status, "REJECTED");
  assert.equal(fakeResult.outcome, "ERROR");
  assert.match(fakeResult.stderr, /binary digest/);
  rmSync(root, { recursive: true, force: true });

  const unknownSmt = [
    "(set-option :rlimit 1)", "(declare-const x Int)", "(assert (> x 0))", "(check-sat)", "",
  ].join("\n");
  const unknown = runFrontendSolver(unknownSmt);
  assert.equal(unknown.outcome, "UNKNOWN");
  assert.equal(unknown.proof_status, "NOT_PROVED");

  const nonzero = runFrontendSolver("(assert\n");
  assert.equal(nonzero.outcome, "ERROR");
  assert.notEqual(nonzero.exit_code, 0);
  assert.equal(nonzero.proof_status, "NOT_PROVED");

  const noisy = runFrontendSolver('(echo "extra")\n(check-sat)\n');
  assert.equal(noisy.outcome, "ERROR");
  assert.equal(noisy.proof_status, "NOT_PROVED");
});

test("campaign materializes nine reusable projects, 72 linked route proofs, byte spans, and fail-closed drift verification", () => {
  const root = mkdtempSync(join(tmpdir(), "elmos-frontend-formal-"));
  const output = join(root, "campaign");
  try {
    const campaign = materializeFrontendFormalCampaign(output) as {
      profile_count: number;
      route_count: number;
      profiles: Array<Record<string, unknown>>;
      routes: Array<Record<string, unknown>>;
      counts: Record<string, number>;
      unconditional_proof: boolean;
      certification: string;
    };
    assert.equal(campaign.profile_count, 9);
    assert.equal(campaign.route_count, 72);
    assert.equal(campaign.profiles.length, 9);
    assert.equal(campaign.routes.length, 72);
    assert.equal(campaign.counts.PROVED_UNDER_ASSUMPTIONS, 72);
    assert.equal(campaign.unconditional_proof, false);
    assert.equal(campaign.certification, "NOT_CERTIFIED");
    assert.deepEqual(verifyFrontendFormalCampaign(output), []);

    const first = campaign.routes[0]!;
    const formalPath = join(output, ...String(first.formal_input_path).split("/"));
    assert.equal(sha256Bytes(readFileSync(formalPath, "utf8")), first.formal_input_digest);
    const routeRoot = join(output, "routes", String(first.route_id));
    const chunks = JSON.parse(readFileSync(join(routeRoot, "chunks.json"), "utf8")) as { chunks: Array<Record<string, unknown>> };
    assert.equal(new Set(chunks.chunks.map(chunk => chunk.pointer)).size, 33);
    for (const chunk of chunks.chunks) {
      assert.equal(chunk.pointer_standard, "RFC6901");
      for (const side of ["source", "target"]) {
        const span = chunk[side] as Record<string, unknown>;
        assert.equal(typeof span.start_byte, "number");
        assert.equal(typeof span.end_byte, "number");
        assert.match(String(span.content_hash), /^sha256:[a-f0-9]{64}$/);
        assert.match(String(span.subtree_hash), /^sha256:[a-f0-9]{64}$/);
      }
    }
    const layered = JSON.parse(readFileSync(join(routeRoot, "layered-result.json"), "utf8")) as Record<string, unknown>;
    assert.equal(layered.status, "PROVED_UNDER_ASSUMPTIONS");
    assert.equal(layered.unconditional_proof, false);

    const links = layered.links as Record<string, string>;
    const artifactKinds = ["formal_input_path", "behavior_path", "chunks_path", "source_model_path", "target_model_path", "smt2_path", "solver_result_path"] as const;
    const tamperedArtifacts: Array<{ path: string; bytes: string; routeId: string }> = [];
    for (const [index, kind] of artifactKinds.entries()) {
      const routeRow = campaign.routes[index]!;
      const routeDirectory = join(output, "routes", String(routeRow.route_id));
      const routeLayered = JSON.parse(readFileSync(join(routeDirectory, "layered-result.json"), "utf8")) as { links: Record<string, string> };
      const relativePath = kind === "formal_input_path" ? String(routeRow.formal_input_path) : routeLayered.links[kind]!;
      const path = join(output, ...relativePath.split("/"));
      const bytes = readFileSync(path, "utf8");
      tamperedArtifacts.push({ path, bytes, routeId: String(routeRow.route_id) });
      writeFileSync(path, `${bytes} `, "utf8");
    }
    const artifactErrors = verifyFrontendFormalCampaign(output);
    for (const artifact of tamperedArtifacts) assert.ok(artifactErrors.some(error => error.startsWith(`${artifact.routeId}:`)), `artifact tamper passed: ${artifact.path}`);
    for (const artifact of tamperedArtifacts) writeFileSync(artifact.path, artifact.bytes, "utf8");

    const campaignPath = join(output, "frontend-formal-route-campaign.json");
    const campaignBytes = readFileSync(campaignPath, "utf8");
    const duplicateCampaign = JSON.parse(campaignBytes) as { routes: Array<Record<string, unknown>> };
    duplicateCampaign.routes[duplicateCampaign.routes.length - 1] = structuredClone(duplicateCampaign.routes[0]!);
    writeFileSync(campaignPath, `${JSON.stringify(duplicateCampaign, null, 2)}\n`, "utf8");
    assert.ok(verifyFrontendFormalCampaign(output).some(error => /duplicated|closure/.test(error)));
    writeFileSync(campaignPath, campaignBytes, "utf8");

    const escapedCampaign = JSON.parse(campaignBytes) as { routes: Array<Record<string, unknown>> };
    escapedCampaign.routes[0]!.formal_input_path = "../formal-input.json";
    writeFileSync(campaignPath, `${JSON.stringify(escapedCampaign, null, 2)}\n`, "utf8");
    assert.ok(verifyFrontendFormalCampaign(output).some(error => /unsafe|non-canonical/.test(error)));
    writeFileSync(campaignPath, campaignBytes, "utf8");

    const solverPath = join(output, ...links.solver_result_path!.split("/"));
    const layeredPath = join(routeRoot, "layered-result.json");
    const solverBytes = readFileSync(solverPath, "utf8");
    const layeredBytes = readFileSync(layeredPath, "utf8");
    const forgedSolver = JSON.parse(solverBytes) as Record<string, unknown>;
    forgedSolver.solver_binary_sha256 = `sha256:${"0".repeat(64)}`;
    const forgedSolverBytes = `${JSON.stringify(forgedSolver, null, 2)}\n`;
    const forgedLayered = JSON.parse(layeredBytes) as { links: Record<string, unknown> };
    forgedLayered.links.solver_result_digest = sha256Bytes(forgedSolverBytes);
    writeFileSync(solverPath, forgedSolverBytes, "utf8");
    writeFileSync(layeredPath, `${JSON.stringify(forgedLayered, null, 2)}\n`, "utf8");
    assert.ok(verifyFrontendFormalCampaign(output).some(error => /solver identity|locked solver/.test(error)));
    writeFileSync(solverPath, solverBytes, "utf8");
    writeFileSync(layeredPath, layeredBytes, "utf8");

    const profile = campaign.profiles.find(item => item.profile_id === "react")!;
    const appPath = join(output, String(profile.project_path), "src", "App.tsx");
    writeFileSync(appPath, `${readFileSync(appPath, "utf8")}\n// drift\n`, "utf8");
    assert.ok(verifyFrontendFormalCampaign(output).some(error => error.includes("project digest drifted")));
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
