import { createHash } from "node:crypto";
import type { ComponentNode, Finding, Framework, PackageManager, UiSemanticGraph, WorkspaceInventory } from "./domain.js";

type SourceFiles = Readonly<Record<string, string>>;

function finding(code: string, severity: Finding["severity"], path: string, evidence: string): Finding {
  return { code, severity, path, evidence };
}

function parsePackageJson(files: SourceFiles): Readonly<Record<string, unknown>> {
  const raw = files["package.json"];
  if (!raw) return {};
  try {
    const value: unknown = JSON.parse(raw);
    return value !== null && typeof value === "object" ? value as Readonly<Record<string, unknown>> : {};
  } catch {
    return {};
  }
}

function dependencyNames(pkg: Readonly<Record<string, unknown>>): Set<string> {
  const result = new Set<string>();
  for (const key of ["dependencies", "devDependencies", "peerDependencies"] as const) {
    const values = pkg[key];
    if (values && typeof values === "object") Object.keys(values).forEach(name => result.add(name));
  }
  return result;
}

export function discoverWorkspace(snapshotId: string, files: SourceFiles): WorkspaceInventory {
  if (!snapshotId.trim()) throw new Error("snapshotId is required");
  const names = Object.keys(files).sort();
  if (!names.includes("package.json")
      && !names.some(name => /(^|\/)(bower\.json|config\.xml|pubspec\.yaml|oh-package\.json5|app\.json5)$/.test(name))) {
    throw new Error("FRONTEND_WORKSPACE_NOT_FOUND");
  }
  if (names.some(name => name.startsWith("/") || name.split("/").includes(".."))) {
    throw new Error("workspace paths must be relative and contained");
  }

  const lockfiles = names.filter(name => /(^|\/)(package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|bower\.json|pubspec\.lock|oh-package-lock\.json5)$/.test(name));
  const managers = new Set<PackageManager>();
  if (lockfiles.some(name => /package-lock|npm-shrinkwrap/.test(name))) managers.add("NPM");
  if (lockfiles.some(name => name.endsWith("yarn.lock"))) managers.add("YARN_CLASSIC");
  if (lockfiles.some(name => name.endsWith("pnpm-lock.yaml"))) managers.add("PNPM");
  if (lockfiles.some(name => name.endsWith("bower.json"))) managers.add("BOWER");
  if (names.some(name => name.endsWith("pubspec.yaml"))) managers.add("PUB");
  if (names.some(name => name.endsWith("oh-package.json5"))) managers.add("OHPM");
  const packageManager: PackageManager = managers.size === 0 ? "UNKNOWN" : managers.size === 1 ? [...managers][0]! : "MIXED";

  const pkg = parsePackageJson(files);
  const deps = dependencyNames(pkg);
  const allSource = names.filter(name => /\.(?:js|jsx|ts|tsx|vue|svelte|html|dart|ets)$/.test(name)).map(name => files[name] ?? "").join("\n");
  const frameworks = new Set<Framework>();
  if (deps.has("angular") || /angular\.module\s*\(/.test(allSource)) frameworks.add("ANGULARJS");
  if (deps.has("@angular/core")) frameworks.add("ANGULAR");
  const vueVersion = String((pkg.dependencies as Record<string, unknown> | undefined)?.vue ?? "");
  if (vueVersion && /(?:\^|~|>=|^|\s)2\./.test(vueVersion)) frameworks.add("VUE2");
  if (vueVersion && /(?:\^|~|>=|^|\s)3\./.test(vueVersion)) frameworks.add("VUE3");
  if (deps.has("react-native") || /from\s+['"]react-native['"]/.test(allSource)) frameworks.add("REACT_NATIVE");
  else if (deps.has("react") || /React\.(?:Component|PureComponent)/.test(allSource)) frameworks.add("REACT");
  if (deps.has("jquery") || /\$\s*\([^)]*\)\.(?:on|html|ajax|ready)/.test(allSource)) frameworks.add("JQUERY");
  if (deps.has("svelte") || names.some(name => name.endsWith(".svelte"))) frameworks.add("SVELTE");
  if (names.some(name => name.endsWith("pubspec.yaml"))
      && (/\bflutter\s*:\s*\n\s*sdk\s*:\s*flutter\b/.test(Object.values(files).join("\n"))
        || names.some(name => name.endsWith(".dart")))) frameworks.add("FLUTTER");
  if (names.some(name => name.endsWith(".ets"))
      || names.some(name => /(^|\/)(oh-package\.json5|module\.json5|app\.json5)$/.test(name))) frameworks.add("HARMONY_ARKUI");
  if (frameworks.size === 0) frameworks.add("UNKNOWN");

  const buildTools = [
    ["angular.json", "ANGULAR_CLI"], ["vite.config", "VITE"], ["webpack.config", "WEBPACK"],
    ["rollup.config", "ROLLUP"], ["gulpfile", "GULP"], ["Gruntfile", "GRUNT"],
    ["bower.json", "BOWER"], ["electron-builder", "ELECTRON_BUILDER"],
    ["pubspec.yaml", "FLUTTER"], ["hvigorfile", "HVIGOR"], ["build-profile.json5", "HVIGOR"]
  ].filter(([prefix]) => names.some(name => name.includes(prefix!))).map(([, tool]) => tool!);

  const platforms = new Set<WorkspaceInventory["platforms"][number]>();
  if ([...frameworks].some(value => ["ANGULARJS", "ANGULAR", "VUE2", "VUE3", "REACT", "JQUERY", "SVELTE"].includes(value))
      || names.some(name => name.endsWith(".html"))) platforms.add("WEB");
  if (deps.has("electron") || names.some(name => /electron|preload/.test(name))) platforms.add("DESKTOP");
  if (names.some(name => /android|build\.gradle|AndroidManifest/.test(name))) platforms.add("ANDROID");
  if (names.some(name => /ios|\.xcodeproj|AppDelegate|\.swift$/.test(name))) platforms.add("IOS");
  if (frameworks.has("REACT_NATIVE") && !platforms.has("ANDROID") && !platforms.has("IOS")) {
    platforms.add("ANDROID"); platforms.add("IOS"); platforms.add("WEB");
  }
  if (frameworks.has("FLUTTER") && platforms.size === 0) {
    platforms.add("ANDROID"); platforms.add("IOS"); platforms.add("WEB");
  }
  if (frameworks.has("HARMONY_ARKUI")) platforms.add("HARMONYOS");
  if (platforms.size === 0) platforms.add("WEB");

  const findings: Finding[] = [];
  if (managers.size > 1) findings.push(finding("MULTIPLE_LOCKFILES", "ERROR", ".", lockfiles.join(",")));
  if (packageManager === "UNKNOWN") findings.push(finding("FRONTEND_PACKAGE_MANAGER_UNRESOLVED", "ERROR", "package.json", "no lockfile"));
  if (frameworks.has("ANGULARJS")) findings.push(finding("ANGULARJS_EOL", "ERROR", "package.json", "angular dependency or module"));
  if (frameworks.has("VUE2")) findings.push(finding("VUE2_EOL", "ERROR", "package.json", vueVersion));
  if (names.some(name => /bower\.json|gulpfile|Gruntfile|browserify|requirejs/i.test(name))) findings.push(finding("LEGACY_BUILD_TOOL", "WARNING", ".", "legacy build manifest"));
  for (const name of names.filter(name => /(?:^|\/)\.env|config/i.test(name))) {
    const value = files[name] ?? "";
    if (/(?:NEXT_PUBLIC|VITE|REACT_APP)_[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PRIVATE_KEY)\s*=/.test(value)) {
      findings.push(finding("CLIENT_SECRET_EXPOSURE", "CRITICAL", name, "public environment variable has secret-like name"));
    }
  }

  const entryPoints = names.filter(name => /(?:^|\/)(?:index|Index|main|bootstrap|App|AppDelegate|EntryAbility)\.(?:html|js|jsx|ts|tsx|vue|svelte|swift|dart|ets)$/.test(name));
  return {
    snapshotId,
    packageManager,
    lockfiles,
    frameworks: [...frameworks].sort(),
    buildTools: [...new Set(buildTools)].sort(),
    platforms: [...platforms].sort(),
    entryPoints,
    findings
  };
}

export function buildUiSemanticGraph(applicationId: string, files: SourceFiles): UiSemanticGraph {
  if (!applicationId.trim()) throw new Error("applicationId is required");
  const components: ComponentNode[] = [];
  const routes = new Map<string, { components: Set<string>; permissions: Set<string>; confidence: number }>();
  const findings: Finding[] = [];
  for (const [path, source] of Object.entries(files).sort(([a], [b]) => a.localeCompare(b))) {
    if (!/\.(?:js|jsx|ts|tsx|vue|svelte|html|dart|ets)$/.test(path)) continue;
    const framework: Framework = path.endsWith(".dart") || /extends\s+(?:StatelessWidget|StatefulWidget)/.test(source) ? "FLUTTER"
      : path.endsWith(".ets") || /@(?:Entry|Component)\b/.test(source) ? "HARMONY_ARKUI"
      : path.endsWith(".svelte") ? "SVELTE"
      : /angular\.module|\$scope/.test(source) ? "ANGULARJS"
      : /defineComponent|<template>/.test(source) ? (/Vue\.component/.test(source) ? "VUE2" : "VUE3")
      : /from\s+['"]react-native['"]/.test(source) ? "REACT_NATIVE"
      : /React\.(?:Component|PureComponent)|useState|function\s+[A-Z]/.test(source) ? "REACT"
      : /\$\s*\(/.test(source) ? "JQUERY" : "UNKNOWN";
    const componentNames = [...source.matchAll(/(?:class|struct|function|component:\s*|name:\s*)[ '\"]*([A-Z][A-Za-z0-9_]*)/g)]
      .map(match => match[1] ?? "Anonymous");
    if (path.endsWith(".svelte") && componentNames.length === 0) {
      componentNames.push(path.split("/").pop()?.replace(/\.svelte$/, "") ?? "SvelteComponent");
    }
    for (const componentName of componentNames) {
      const componentId = `${path}#${componentName}`;
      components.push({
        componentId,
        framework,
        sourcePath: path,
        stateKinds: [
          /localStorage/.test(source) ? "LOCAL_STORAGE" : "LOCAL_COMPONENT",
          /(?:redux|vuex|pinia|ngrx)/i.test(source) ? "GLOBAL_STORE" : "LOCAL_COMPONENT"
        ].filter((value, index, values) => values.indexOf(value) === index),
        eventKinds: [
          /onClick|\.click\s*\(|@click/.test(source) ? "USER_CLICK" : "USER_INPUT",
          /fetch\s*\(|axios|\$http|\$\.ajax/.test(source) ? "API_RESPONSE" : "USER_INPUT"
        ].filter((value, index, values) => values.indexOf(value) === index)
      });
    }
    for (const match of source.matchAll(/(?:path\s*:\s*|Route\s+path=|\.when\s*\()\s*[{'\"]*([^'\"},\s]+)/g)) {
      const routePath = match[1] ?? "";
      if (!routePath.startsWith("/")) continue;
      const current = routes.get(routePath) ?? { components: new Set<string>(), permissions: new Set<string>(), confidence: 0.9 };
      componentNames.forEach(componentName => current.components.add(`${path}#${componentName}`));
      for (const permission of source.matchAll(/(?:permission|role|authority)\s*[:=(]\s*['\"]([^'\"]+)/gi)) current.permissions.add(permission[1] ?? "");
      routes.set(routePath, current);
    }
    if (/import\s*\(\s*[^'\"]|component\s*:\s*[a-zA-Z_$][\w$]*\s*[,}]/.test(source)) {
      findings.push(finding("DYNAMIC_UI_DEPENDENCY", "WARNING", path, "runtime component target unresolved"));
    }
    if (/dangerouslySetInnerHTML|\.html\s*\(|innerHTML\s*=/.test(source)) findings.push(finding("UNSAFE_HTML", "ERROR", path, "HTML injection sink"));
  }
  return {
    routes: [...routes.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([path, value]) => ({
      routeId: createHash("sha256").update(`${applicationId}:${path}`).digest("hex").slice(0, 16),
      applicationId,
      path,
      routeType: path.includes(":") ? "PARAMETERIZED" : "STATIC",
      componentIds: [...value.components].sort(),
      requiredPermissions: [...value.permissions].filter(Boolean).sort(),
      confidence: value.confidence
    })),
    components: components.sort((a, b) => a.componentId.localeCompare(b.componentId)),
    findings
  };
}
