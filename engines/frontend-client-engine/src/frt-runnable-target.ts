import type { FrtRouteStack, PortableUiIr } from "./frt-route-ir.js";

function json(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function openApi(target: FrtRouteStack): string {
  return json({
    openapi: "3.0.3",
    info: { title: `FRT ${target} runnable smoke contract`, version: "1.0.0" },
    paths: {
      "/counter": {
        get: {
          operationId: "getCounterRoute",
          responses: { "200": { description: "The generated target started and answered." } },
        },
      },
    },
  });
}

function nodePortPrelude(): readonly string[] {
  return [
    'const port = Number.parseInt(process.env.SMOKE_PORT ?? process.env.PORT ?? "", 10);',
    'if (!Number.isInteger(port) || port < 1024 || port > 65535) {',
    '  process.stderr.write("FRT_SMOKE_PORT_INVALID\\n");',
    '  process.exit(2);',
    '}',
  ];
}

function reactServer(ir: PortableUiIr): string {
  return [
    'import { createServer } from "node:http";',
    'import React from "react";',
    'import { renderToStaticMarkup } from "react-dom/server";',
    ...nodePortPrelude(),
    "function document() {",
    "  const app = React.createElement(\"main\", { \"aria-label\": "
      + `${JSON.stringify(ir.accessibility.mainLabel)} },`,
    `    React.createElement("h1", null, ${JSON.stringify(ir.view.title)}),`,
    `    React.createElement("button", { "aria-label": ${JSON.stringify(ir.accessibility.buttonLabel)} }, ${JSON.stringify(ir.view.buttonLabel)}),`,
    `    React.createElement("p", { "aria-live": "polite" }, ${JSON.stringify(String(ir.view.initialCount))}),`,
    "  );",
    `  return ${JSON.stringify(`<!doctype html><html lang="en"><meta charset="utf-8"><title>${ir.view.title}</title><body>`)} + renderToStaticMarkup(app) + "</body></html>";`,
    "}",
    "const server = createServer((request, response) => {",
    '  if (request.url === "/health") { response.writeHead(200, { "content-type": "application/json" }); response.end("{\\\"status\\\":\\\"ok\\\"}"); return; }',
    '  if (request.url === "/" || request.url === "/counter") { response.writeHead(200, { "content-type": "text/html; charset=utf-8" }); response.end(document()); return; }',
    "  response.writeHead(404); response.end();",
    "});",
    'server.listen(port, "127.0.0.1");',
    "",
  ].join("\n");
}

function vue3Server(ir: PortableUiIr): string {
  return [
    'import { createServer } from "node:http";',
    'import { createSSRApp, h } from "vue";',
    'import { renderToString } from "@vue/server-renderer";',
    ...nodePortPrelude(),
    "async function document() {",
    "  const app = createSSRApp({ render: () => h(\"main\", { \"aria-label\": "
      + `${JSON.stringify(ir.accessibility.mainLabel)} }, [`,
    `    h("h1", null, ${JSON.stringify(ir.view.title)}),`,
    `    h("button", { "aria-label": ${JSON.stringify(ir.accessibility.buttonLabel)} }, ${JSON.stringify(ir.view.buttonLabel)}),`,
    `    h("p", { "aria-live": "polite" }, ${JSON.stringify(String(ir.view.initialCount))}),`,
    "  ]) });",
    "  const body = await renderToString(app);",
    `  return ${JSON.stringify(`<!doctype html><html lang="en"><meta charset="utf-8"><title>${ir.view.title}</title><body>`)} + body + "</body></html>";`,
    "}",
    "const server = createServer(async (request, response) => {",
    '  if (request.url === "/health") { response.writeHead(200, { "content-type": "application/json" }); response.end("{\\\"status\\\":\\\"ok\\\"}"); return; }',
    '  if (request.url === "/" || request.url === "/counter") { response.writeHead(200, { "content-type": "text/html; charset=utf-8" }); response.end(await document()); return; }',
    "  response.writeHead(404); response.end();",
    "});",
    'server.listen(port, "127.0.0.1");',
    "",
  ].join("\n");
}

function vue2Server(ir: PortableUiIr): string {
  return [
    'import { createServer } from "node:http";',
    'import Vue from "vue";',
    'import rendererPackage from "vue-server-renderer";',
    ...nodePortPrelude(),
    "const renderer = rendererPackage.createRenderer();",
    "async function document() {",
    "  const app = new Vue({ render: (h) => h(\"main\", { attrs: { \"aria-label\": "
      + `${JSON.stringify(ir.accessibility.mainLabel)} } }, [`,
    `    h("h1", ${JSON.stringify(ir.view.title)}),`,
    `    h("button", { attrs: { "aria-label": ${JSON.stringify(ir.accessibility.buttonLabel)} } }, ${JSON.stringify(ir.view.buttonLabel)}),`,
    `    h("p", { attrs: { "aria-live": "polite" } }, ${JSON.stringify(String(ir.view.initialCount))}),`,
    "  ]) });",
    "  const body = await renderer.renderToString(app);",
    `  return ${JSON.stringify(`<!doctype html><html lang="en"><meta charset="utf-8"><title>${ir.view.title}</title><body>`)} + body + "</body></html>";`,
    "}",
    "const server = createServer(async (request, response) => {",
    '  if (request.url === "/health") { response.writeHead(200, { "content-type": "application/json" }); response.end("{\\\"status\\\":\\\"ok\\\"}"); return; }',
    '  if (request.url === "/" || request.url === "/counter") { response.writeHead(200, { "content-type": "text/html; charset=utf-8" }); response.end(await document()); return; }',
    "  response.writeHead(404); response.end();",
    "});",
    'server.listen(port, "127.0.0.1");',
    "",
  ].join("\n");
}

function statusSidecar(target: "WECHAT_MINI_PROGRAM" | "ARKUI"): string {
  const launch = target === "WECHAT_MINI_PROGRAM" ? [
    'const cli = process.env.ELMOS_WECHAT_CLI ?? (process.platform === "darwin" ? "/Applications/wechatwebdevtools.app/Contents/MacOS/cli" : "cli");',
    'const controlPort = process.env.ELMOS_WECHAT_CONTROL_PORT ?? "19420";',
    'const launched = spawnSync(cli, ["open", "--project", process.cwd(), "--port", controlPort, "--lang", "en", "--disable-gpu"], { encoding: "utf8", input: "y\\n", timeout: 120_000 });',
    'if (launched.status !== 0) { process.stderr.write((launched.stderr || "WECHAT_DEVTOOLS_LAUNCH_FAILED").slice(-4000)); process.exit(3); }',
  ] : [
    'function resolveCommand(configured, names) {',
    '  if (configured) return configured;',
    '  const finder = process.platform === "win32" ? "where" : "which";',
    '  for (const name of names) { const found = spawnSync(finder, [name], { encoding: "utf8" }); if (found.status === 0) return found.stdout.trim().split(/\\r?\\n/)[0]; }',
    '  return null;',
    '}',
    'const hvigor = resolveCommand(process.env.ELMOS_HVIGORW, ["hvigorw", "hvigor"]);',
    'const hdc = resolveCommand(process.env.ELMOS_HDC, ["hdc"]);',
    'if (!hvigor || !hdc) { process.stderr.write("ARKUI_HVIGOR_OR_HDC_UNAVAILABLE\\n"); process.exit(3); }',
    'const built = spawnSync(hvigor, ["assembleHap", "--mode", "module", "-p", "product=default", "-p", "module=entry@default"], { encoding: "utf8", timeout: 600_000 });',
    'if (built.status !== 0) { process.stderr.write((built.stderr || "ARKUI_BUILD_FAILED").slice(-4000)); process.exit(3); }',
    'function filesBelow(root) { const output = []; for (const entry of readdirSync(root, { withFileTypes: true })) { const item = join(root, entry.name); if (entry.isDirectory()) output.push(...filesBelow(item)); else output.push(item); } return output; }',
    'const hap = filesBelow(join(process.cwd(), "entry")).find((item) => item.endsWith(".hap"));',
    'if (!hap) { process.stderr.write("ARKUI_HAP_NOT_FOUND\\n"); process.exit(3); }',
    'const installed = spawnSync(hdc, ["install", "-r", hap], { encoding: "utf8", timeout: 120_000 });',
    'if (installed.status !== 0) { process.stderr.write((installed.stderr || "ARKUI_INSTALL_FAILED").slice(-4000)); process.exit(3); }',
    'const launched = spawnSync(hdc, ["shell", "aa", "start", "-a", "EntryAbility", "-b", "io.elmos.frtroute"], { encoding: "utf8", timeout: 60_000 });',
    'if (launched.status !== 0) { process.stderr.write((launched.stderr || "ARKUI_LAUNCH_FAILED").slice(-4000)); process.exit(3); }',
  ];
  const imports = target === "ARKUI"
    ? ['import { readdirSync } from "node:fs";', 'import { join } from "node:path";']
    : [];
  const close = target === "WECHAT_MINI_PROGRAM"
    ? 'spawnSync(cli, ["close", "--project", process.cwd(), "--port", controlPort], { encoding: "utf8", timeout: 30_000 });'
    : 'spawnSync(hdc, ["shell", "aa", "force-stop", "io.elmos.frtroute"], { encoding: "utf8", timeout: 30_000 });';
  return [
    'import { createServer } from "node:http";',
    'import { spawnSync } from "node:child_process";',
    ...imports,
    ...nodePortPrelude(),
    ...launch,
    `const state = ${JSON.stringify(target)};`,
    "const server = createServer((request, response) => {",
    '  if (request.url === "/health" || request.url === "/counter") { response.writeHead(200, { "content-type": "application/json" }); response.end(JSON.stringify({ status: "launched", target: state })); return; }',
    "  response.writeHead(404); response.end();",
    "});",
    'server.listen(port, "127.0.0.1");',
    "let closing = false;",
    "function shutdown() { if (closing) return; closing = true; server.close(() => { " + close + " process.exit(0); }); }",
    'process.once("SIGTERM", shutdown);',
    'process.once("SIGINT", shutdown);',
    "",
  ].join("\n");
}

function flutterWebIndex(title: string): string {
  return [
    "<!doctype html>",
    '<html lang="en">',
    '<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">',
    `<title>${title.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")}</title></head>`,
    '<body><script src="flutter_bootstrap.js" async></script></body>',
    "</html>",
    "",
  ].join("\n");
}

export function attachRunnableTarget(
  input: Readonly<Record<string, string>>,
  ir: PortableUiIr,
  target: FrtRouteStack,
): Record<string, string> {
  const files: Record<string, string> = { ...input, "openapi.json": openApi(target) };
  if (target === "React" || target === "Vue 2" || target === "Vue 3") {
    const manifest = JSON.parse(files["package.json"] ?? "{}") as Record<string, unknown> & {
      scripts?: Record<string, string>;
      dependencies?: Record<string, string>;
    };
    manifest.scripts = { ...manifest.scripts, "start:smoke": "node server.mjs" };
    if (target === "Vue 2") {
      manifest.dependencies = { ...manifest.dependencies, "vue-server-renderer": "2.7.16" };
    } else if (target === "Vue 3") {
      manifest.dependencies = { ...manifest.dependencies, "@vue/server-renderer": "3.5.39" };
    }
    files["package.json"] = json(manifest);
    files["server.mjs"] = target === "React" ? reactServer(ir)
      : target === "Vue 3" ? vue3Server(ir) : vue2Server(ir);
    return files;
  }
  if (target === "WeChat Mini Program") {
    files["app.js"] = "App({});\n";
    files["scripts/frt-smoke-start.mjs"] = statusSidecar("WECHAT_MINI_PROGRAM");
    return files;
  }
  if (target === "ArkUI") {
    files["entry/src/main/module.json5"] = json({ module: {
      name: "entry",
      type: "entry",
      srcEntry: "./ets/entryability/EntryAbility.ets",
      deviceTypes: ["phone", "tablet"],
      pages: "$profile:main_pages",
      abilities: [{
        name: "EntryAbility",
        srcEntry: "./ets/entryability/EntryAbility.ets",
        description: "$string:ability_desc",
        label: "$string:EntryAbility_label",
        startWindowBackground: "$color:start_window_background",
        exported: true,
        skills: [{ entities: ["entity.system.home"], actions: ["ohos.want.action.home"] }],
      }],
    } });
    files["entry/src/main/ets/entryability/EntryAbility.ets"] = [
      "import { AbilityConstant, UIAbility, Want } from '@kit.AbilityKit';",
      "import { hilog } from '@kit.PerformanceAnalysisKit';",
      "import { window } from '@kit.ArkUI';",
      "export default class EntryAbility extends UIAbility {",
      "  onCreate(_want: Want, _launchParam: AbilityConstant.LaunchParam): void { hilog.info(0x0000, 'FRT', 'EntryAbility created'); }",
      "  onWindowStageCreate(windowStage: window.WindowStage): void { windowStage.loadContent('pages/Index'); }",
      "}",
      "",
    ].join("\n");
    files["entry/src/main/resources/base/element/string.json"] = json({ string: [
      { name: "EntryAbility_label", value: ir.view.title },
      { name: "ability_desc", value: "FRT generated counter route" },
    ] });
    files["entry/src/main/resources/base/element/color.json"] = json({ color: [
      { name: "start_window_background", value: "#FFFFFF" },
    ] });
    files["scripts/frt-smoke-start.mjs"] = statusSidecar("ARKUI");
    return files;
  }
  files[".metadata"] = [
    "# This file tracks properties of this Flutter project.",
    "version:",
    "  revision: \"3.44.1\"",
    "  channel: \"stable\"",
    "project_type: app",
    "",
  ].join("\n");
  files["web/index.html"] = flutterWebIndex(ir.view.title);
  files["web/manifest.json"] = json({
    name: ir.view.title,
    short_name: ir.view.title,
    start_url: ".",
    display: "standalone",
    background_color: "#FFFFFF",
    theme_color: ir.style.accentColor,
    description: "FRT generated counter route",
    orientation: "portrait-primary",
    prefer_related_applications: false,
  });
  return files;
}
