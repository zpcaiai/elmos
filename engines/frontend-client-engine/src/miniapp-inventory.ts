import { createHash } from "node:crypto";

import {
  MINIAPP_SOURCE_LABELS,
  type MiniappConfigurationEvidence,
  type MiniappConfigurationKind,
  type MiniappDeclaredRuntimeEvidence,
  type MiniappDependencyEvidence,
  type MiniappLockedDependencyEvidence,
  type MiniappFrameworkCandidate,
  type MiniappFrameworkConflict,
  type MiniappFrameworkSignal,
  type MiniappFrameworkSignalKind,
  type MiniappInventoryFile,
  type MiniappInventoryFileKind,
  type MiniappInventoryFinding,
  type MiniappInventoryInput,
  type MiniappInventoryInputFile,
  type MiniappSourceInventory,
  type MiniappSourceLabel,
} from "./miniapp-types.js";
import {
  MiniappContractValidationError,
  normalizeMiniappRelativePath,
  validateMiniappInventoryLimits,
} from "./miniapp-contract-validation.js";

const revisionPattern = /^(?:[a-f0-9]{7,64}|sha256:[a-f0-9]{64})$/;
const sha256Pattern = /^sha256:[a-f0-9]{64}$/;
const inventoryIdPattern = /^inv-[a-z0-9][a-z0-9-]{2,63}$/;
const safeSecretReference = /^(?:vault|secret|kms):\/\/[A-Za-z0-9][A-Za-z0-9._/@:-]{0,511}$/;
const secretAssignment = /["']?([A-Za-z_][A-Za-z0-9_-]*)["']?\s*[:=]\s*["']([^"'\r\n]+)["']/gi;
const templateSecretAssignment = /([A-Za-z_][A-Za-z0-9_-]*)\s*[:=]\s*`([^`\r\n]*)`/gi;
const dotenvAssignment = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/gm;
const configLineSecretAssignment = /^\s*["']?([A-Za-z_][A-Za-z0-9_.-]*)["']?\s*[:=]\s*(.*?)\s*(?:#.*)?$/gm;
const privateKeyMaterial = /-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/;
const wellKnownToken = /(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})/;
const bearerOrBasicCredential = /\b(?:Bearer|Basic)\s+[A-Za-z0-9+/=_-]{8,}/iu;
const jwtMaterial = /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/u;
const credentialUri = /[A-Za-z][A-Za-z0-9+.-]*:\/\/[^\s/:]+:[^\s/@]+@/u;

const assetExtensions = new Set([
  ".7z", ".avif", ".bin", ".bmp", ".gif", ".gz", ".ico", ".jpeg", ".jpg", ".mp3", ".mp4", ".ogg",
  ".otf", ".pdf", ".png", ".rar", ".svg", ".tar", ".ttf", ".wasm", ".wav", ".webm", ".webp", ".woff", ".woff2", ".zip",
]);
const styleExtensions = new Set([".css", ".less", ".sass", ".scss", ".styl", ".acss", ".ttss", ".wxss"]);
const miniappTemplateExtensions = new Set([".axml", ".swan", ".ttml", ".wxml"]);
const unsupportedSourceExtensions = new Set([".astro", ".coffee", ".elm", ".mdx", ".svelte"]);
const appConfigNames = new Set([
  "app.json", "manifest.json", "mini.project.json", "pages.json", "project.config.json",
]);
const selectionOrder: readonly MiniappSourceLabel[] = [
  "taro", "uni-app", "native-miniapp", "flutter", "vue3", "vue2", "react", "h5", "typescript", "javascript",
];

export class MiniappInventoryError extends Error {
  readonly code: string;
  readonly path: string;

  constructor(code: string, path: string, reason: string) {
    super(`${path}: ${reason}`);
    this.name = "MiniappInventoryError";
    this.code = code;
    this.path = path;
  }
}

function fail(code: string, path: string, reason: string): never {
  throw new MiniappInventoryError(code, path, reason);
}

function plainObject(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return fail("MINIAPP_INVENTORY_INPUT_INVALID", path, "must be an object");
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    return fail("MINIAPP_INVENTORY_INPUT_INVALID", path, "must be a plain object");
  }
  return value as Record<string, unknown>;
}

function exactKeys(value: Readonly<Record<string, unknown>>, path: string, required: readonly string[]): void {
  const allowed = new Set(required);
  for (const key of required) {
    if (!Object.hasOwn(value, key)) fail("MINIAPP_INVENTORY_INPUT_INVALID", `${path}.${key}`, "is required");
  }
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) fail("MINIAPP_INVENTORY_INPUT_INVALID", `${path}.${key}`, "is not allowed");
  }
}

function boundedText(value: unknown, path: string, pattern?: RegExp, maximum = 1024): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum || value !== value.trim()) {
    return fail("MINIAPP_INVENTORY_INPUT_INVALID", path, `must be a trimmed non-empty string of at most ${maximum} characters`);
  }
  if (/[\u0000-\u001f\u007f]/u.test(value) || (pattern && !pattern.test(value))) {
    return fail("MINIAPP_INVENTORY_INPUT_INVALID", path, "has an invalid format");
  }
  return value;
}

function normalizedPath(value: unknown, path: string): string {
  try {
    const result = normalizeMiniappRelativePath(value, path);
    if (result === ".") return fail("MINIAPP_SOURCE_PATH_INVALID", path, "must identify a file, not a directory");
    return result;
  } catch (error) {
    if (error instanceof MiniappContractValidationError) {
      return fail("MINIAPP_SOURCE_PATH_INVALID", error.path, error.message.slice(error.path.length + 2));
    }
    throw error;
  }
}

function bytes(content: string | Uint8Array): Uint8Array {
  return typeof content === "string" ? Buffer.from(content, "utf8") : new Uint8Array(content);
}

function sha256(content: string | Uint8Array): string {
  return `sha256:${createHash("sha256").update(content).digest("hex")}`;
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function fileExtension(path: string): string {
  const base = path.slice(path.lastIndexOf("/") + 1);
  const dot = base.lastIndexOf(".");
  return dot < 0 ? "" : base.slice(dot).toLowerCase();
}

function baseName(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

function explicitlyNonRuntimeText(path: string): boolean {
  const name = baseName(path);
  return /^(?:readme|license|notice|changelog|contributing|code_of_conduct)(?:\..*)?$/iu.test(name)
    || /^(?:package-lock\.json|pnpm-lock\.yaml|yarn\.lock|npm-shrinkwrap\.json)$/u.test(name)
    || /^\.(?:git|docker|eslint|prettier|npm)ignore$/u.test(name);
}

function fileKind(path: string, binary: boolean): MiniappInventoryFileKind {
  if (binary) return "binary";
  const extension = fileExtension(path);
  if (path.endsWith("package.json") || appConfigNames.has(baseName(path))) return "json-config";
  if (baseName(path) === "pubspec.yaml" || extension === ".yaml" || extension === ".yml") return "yaml-config";
  if (extension === ".vue") return "vue-sfc";
  if (extension === ".ts" || extension === ".tsx" || extension === ".mts" || extension === ".cts") return "typescript";
  if (extension === ".js" || extension === ".jsx" || extension === ".mjs" || extension === ".cjs") return "javascript";
  if (extension === ".dart") return "dart";
  if (extension === ".html" || extension === ".htm") return "html";
  if (styleExtensions.has(extension)) return "style";
  if (miniappTemplateExtensions.has(extension)) return "miniapp-template";
  if (assetExtensions.has(extension)) return "asset";
  return "text";
}

function decodeText(content: Uint8Array): string | null {
  if (content.includes(0)) return null;
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(content);
  } catch {
    return null;
  }
}

function assertSafeSecretValue(value: string, path: string, key: string): void {
  const normalized = value.trim().replace(/^(?:["'])(.*)(?:["'])$/u, "$1");
  if (normalized.length === 0) return;
  if (safeSecretReference.test(normalized)) return;
  fail("MINIAPP_UNSAFE_SECRET_VALUE", path, `${key} must contain a vault://, secret://, or kms:// reference, never secret material`);
}

function isSensitiveKey(key: string): boolean {
  const normalized = key.normalize("NFKC").replace(/[^A-Za-z0-9]/gu, "").toLowerCase();
  return /(?:secret|token|password|passwd|credential|credentials|privatekey|apikey|accesskey|accesskeyid|authorization|cookie|session|sessionid|sessionkey)(?:value|material)?$/u.test(normalized);
}

function scanStructuredSecretValues(value: unknown, sourcePath: string): void {
  const pending: Array<{ readonly value: unknown; readonly path: string; readonly depth: number }> = [
    { value, path: sourcePath, depth: 0 },
  ];
  let visited = 0;
  while (pending.length > 0) {
    const item = pending.pop()!;
    visited += 1;
    if (visited > 100_000 || item.depth > 48) {
      fail("MINIAPP_CONFIG_BOUNDS_EXCEEDED", sourcePath, "configuration nesting exceeds safe scan bounds");
    }
    if (Array.isArray(item.value)) {
      item.value.forEach((entry, index) => pending.push({
        value: entry,
        path: `${item.path}[${index}]`,
        depth: item.depth + 1,
      }));
      continue;
    }
    if (!item.value || typeof item.value !== "object") continue;
    const dependencyMap = /\.(?:dependencies|devDependencies|optionalDependencies|overrides|packages|peerDependencies|resolutions)$/u.test(item.path);
    for (const [key, child] of Object.entries(item.value as Readonly<Record<string, unknown>>)) {
      const childPath = `${item.path}.${key}`;
      if (!dependencyMap && isSensitiveKey(key)) {
        if (typeof child !== "string") {
          fail("MINIAPP_UNSAFE_SECRET_VALUE", childPath, `${key} must be one reference string, never an object, array, or embedded secret container`);
        }
        assertSafeSecretValue(child, childPath, key);
      }
      pending.push({ value: child, path: childPath, depth: item.depth + 1 });
    }
  }
}

function assertNoUnsafeSecrets(path: string, text: string): void {
  if (privateKeyMaterial.test(text) || wellKnownToken.test(text) || bearerOrBasicCredential.test(text)
    || jwtMaterial.test(text) || credentialUri.test(text)) {
    fail("MINIAPP_UNSAFE_SECRET_VALUE", path, "contains recognizable secret material");
  }
  const extension = fileExtension(path);
  if (extension !== ".json") {
    secretAssignment.lastIndex = 0;
    for (let match = secretAssignment.exec(text); match; match = secretAssignment.exec(text)) {
      if (isSensitiveKey(match[1]!)) assertSafeSecretValue(match[2]!, path, match[1]!);
    }
    templateSecretAssignment.lastIndex = 0;
    for (let match = templateSecretAssignment.exec(text); match; match = templateSecretAssignment.exec(text)) {
      if (!isSensitiveKey(match[1]!)) continue;
      if (match[2]!.includes("${")) {
        fail("MINIAPP_UNSAFE_SECRET_VALUE", path, `${match[1]} template interpolation cannot prove a reference-only secret boundary`);
      }
      assertSafeSecretValue(match[2]!, path, match[1]!);
    }
  }
  if (baseName(path).startsWith(".env")) {
    dotenvAssignment.lastIndex = 0;
    for (let match = dotenvAssignment.exec(text); match; match = dotenvAssignment.exec(text)) {
      if (isSensitiveKey(match[1]!)) assertSafeSecretValue(match[2]!, path, match[1]!);
    }
  }
  if ([".yaml", ".yml", ".toml", ".ini", ".conf", ".config"].includes(extension)) {
    configLineSecretAssignment.lastIndex = 0;
    for (let match = configLineSecretAssignment.exec(text); match; match = configLineSecretAssignment.exec(text)) {
      if (!isSensitiveKey(match[1]!)) continue;
      if (!match[2]!.trim()) {
        fail("MINIAPP_UNSAFE_SECRET_VALUE", path, `${match[1]} must be one explicit reference string`);
      }
      assertSafeSecretValue(match[2]!, path, match[1]!);
    }
  }
  if (extension === ".json") {
    try {
      scanStructuredSecretValues(JSON.parse(text), path);
    } catch (error) {
      if (error instanceof MiniappInventoryError) throw error;
    }
  }
}

export function validateMiniappInventoryInput(value: unknown): MiniappInventoryInput {
  const candidate = plainObject(value, "inventoryInput");
  exactKeys(candidate, "inventoryInput", [
    "schemaVersion", "inventoryId", "sourceRevision", "sourceSnapshotDigest", "sourceLabelHint", "limits", "files",
  ]);
  if (candidate.schemaVersion !== "1.0") {
    fail("MINIAPP_INVENTORY_INPUT_INVALID", "inventoryInput.schemaVersion", "must equal 1.0");
  }
  let limits: MiniappInventoryInput["limits"];
  try {
    limits = validateMiniappInventoryLimits(candidate.limits, "inventoryInput.limits");
  } catch (error) {
    if (error instanceof MiniappContractValidationError) {
      return fail("MINIAPP_INVENTORY_INPUT_INVALID", error.path, error.message.slice(error.path.length + 2));
    }
    throw error;
  }
  if (!Array.isArray(candidate.files) || candidate.files.length < 1) {
    fail("MINIAPP_INVENTORY_INPUT_INVALID", "inventoryInput.files", "must be a non-empty array");
  }
  if (candidate.files.length > limits.maxFileCount) {
    fail("MINIAPP_FILE_COUNT_LIMIT_EXCEEDED", "inventoryInput.files", `contains more than ${limits.maxFileCount} files`);
  }
  const files: MiniappInventoryInputFile[] = [];
  const seen = new Set<string>();
  let totalBytes = 0;
  candidate.files.forEach((rawFile, index) => {
    const file = plainObject(rawFile, `inventoryInput.files[${index}]`);
    exactKeys(file, `inventoryInput.files[${index}]`, ["path", "content"]);
    const path = normalizedPath(file.path, `inventoryInput.files[${index}].path`);
    if (seen.has(path)) fail("MINIAPP_DUPLICATE_SOURCE_PATH", `inventoryInput.files[${index}].path`, `duplicates ${path}`);
    seen.add(path);
    if (typeof file.content !== "string" && !(file.content instanceof Uint8Array)) {
      fail("MINIAPP_INVENTORY_INPUT_INVALID", `inventoryInput.files[${index}].content`, "must be a string or Uint8Array");
    }
    const copy = typeof file.content === "string" ? file.content : new Uint8Array(file.content);
    const byteCount = bytes(copy).byteLength;
    if (byteCount > limits.maxFileBytes) {
      fail("MINIAPP_FILE_SIZE_LIMIT_EXCEEDED", `inventoryInput.files[${index}].content`, `${path} exceeds ${limits.maxFileBytes} bytes`);
    }
    totalBytes += byteCount;
    if (!Number.isSafeInteger(totalBytes) || totalBytes > limits.maxTotalBytes) {
      fail("MINIAPP_TOTAL_SIZE_LIMIT_EXCEEDED", "inventoryInput.files", `content exceeds ${limits.maxTotalBytes} bytes`);
    }
    files.push({ path, content: copy });
  });
  const hint = candidate.sourceLabelHint;
  if (hint !== "auto" && (typeof hint !== "string" || !MINIAPP_SOURCE_LABELS.includes(hint as MiniappSourceLabel))) {
    fail("MINIAPP_INVENTORY_INPUT_INVALID", "inventoryInput.sourceLabelHint", "must be auto or a known source label");
  }
  return {
    schemaVersion: "1.0",
    inventoryId: boundedText(candidate.inventoryId, "inventoryInput.inventoryId", inventoryIdPattern, 68),
    sourceRevision: boundedText(candidate.sourceRevision, "inventoryInput.sourceRevision", revisionPattern, 71),
    sourceSnapshotDigest: boundedText(candidate.sourceSnapshotDigest, "inventoryInput.sourceSnapshotDigest", sha256Pattern, 71),
    sourceLabelHint: hint as MiniappSourceLabel | "auto",
    limits,
    files: files.sort((left, right) => compareText(left.path, right.path)),
  };
}

interface MutableScanState {
  readonly signals: Map<MiniappSourceLabel, MiniappFrameworkSignal[]>;
  readonly dependencies: MiniappDependencyEvidence[];
  readonly lockedDependencies: MiniappLockedDependencyEvidence[];
  readonly declaredRuntimes: MiniappDeclaredRuntimeEvidence[];
  readonly configurations: MiniappConfigurationEvidence[];
  readonly entrypoints: Set<string>;
  readonly routes: Set<string>;
  readonly components: Set<string>;
  readonly stores: Set<string>;
  readonly assets: Set<string>;
  readonly platformApiSignals: Set<string>;
  readonly configErrors: Array<{ readonly path: string; readonly message: string }>;
}

function addSignal(
  state: MutableScanState,
  sourceLabel: MiniappSourceLabel,
  kind: MiniappFrameworkSignalKind,
  path: string,
  detail: string,
  weight: number,
): void {
  const signals = state.signals.get(sourceLabel) ?? [];
  if (!signals.some(signal => signal.kind === kind && signal.path === path && signal.detail === detail)) {
    signals.push({ sourceLabel, kind, path, detail, weight });
    state.signals.set(sourceLabel, signals);
  }
}

function stringRecord(value: unknown): Readonly<Record<string, string>> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const entries = Object.entries(value as Readonly<Record<string, unknown>>);
  if (!entries.every(([, item]) => typeof item === "string" && item.length > 0)) return null;
  return Object.fromEntries(entries) as Readonly<Record<string, string>>;
}

function vueMajor(version: string): 2 | 3 | null {
  const match = /(?:^|[^0-9])([23])(?:\.|$)/u.exec(version);
  return match?.[1] === "2" ? 2 : match?.[1] === "3" ? 3 : null;
}

function dependencySignals(state: MutableScanState, dependency: MiniappDependencyEvidence): void {
  const name = dependency.name.toLowerCase();
  if (name === "vue") {
    const major = vueMajor(dependency.version);
    if (major === 2) addSignal(state, "vue2", "manifest-dependency", dependency.sourcePath, `vue@${dependency.version}`, 0.92);
    else if (major === 3) addSignal(state, "vue3", "manifest-dependency", dependency.sourcePath, `vue@${dependency.version}`, 0.92);
    else {
      addSignal(state, "vue2", "manifest-dependency", dependency.sourcePath, "vue with unresolved major", 0.45);
      addSignal(state, "vue3", "manifest-dependency", dependency.sourcePath, "vue with unresolved major", 0.45);
    }
  }
  if (name === "react" || name === "react-dom") {
    addSignal(state, "react", "manifest-dependency", dependency.sourcePath, `${dependency.name}@${dependency.version}`, 0.86);
  }
  if (name === "typescript") {
    addSignal(state, "typescript", "manifest-dependency", dependency.sourcePath, `typescript@${dependency.version}`, 0.82);
  }
  if (name === "@tarojs/taro" || name.startsWith("@tarojs/")) {
    addSignal(state, "taro", "manifest-dependency", dependency.sourcePath, `${dependency.name}@${dependency.version}`, 0.96);
  }
  if (name.startsWith("@dcloudio/") || name === "uni-app") {
    addSignal(state, "uni-app", "manifest-dependency", dependency.sourcePath, `${dependency.name}@${dependency.version}`, 0.96);
  }
}

function parsePackageJson(path: string, digest: string, text: string, state: MutableScanState): boolean {
  try {
    const value = JSON.parse(text) as unknown;
    scanStructuredSecretValues(value, path);
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("root must be an object");
    const manifest = value as Readonly<Record<string, unknown>>;
    const groups = [
      ["dependencies", "direct"],
      ["optionalDependencies", "direct"],
      ["peerDependencies", "direct"],
      ["devDependencies", "dev"],
    ] as const;
    for (const [field, scope] of groups) {
      if (manifest[field] === undefined) continue;
      const entries = stringRecord(manifest[field]);
      if (!entries) throw new Error(`${field} must map package names to versions`);
      for (const [name, version] of Object.entries(entries)) {
        const dependency: MiniappDependencyEvidence = { name, version, scope, sourcePath: path };
        state.dependencies.push(dependency);
        dependencySignals(state, dependency);
      }
    }
    const scripts = manifest.scripts === undefined ? {} : stringRecord(manifest.scripts);
    if (manifest.scripts !== undefined && !scripts) throw new Error("scripts must map names to strings");
    const engines = manifest.engines === undefined ? {} : stringRecord(manifest.engines);
    if (manifest.engines !== undefined && !engines) throw new Error("engines must map runtime names to versions");
    const nodeVersion = engines?.node;
    if (nodeVersion && /^[0-9]+(?:\.[0-9]+){2,3}(?:-[0-9A-Za-z.-]+)?$/u.test(nodeVersion)) {
      state.declaredRuntimes.push({
        runtime: "node",
        version: nodeVersion,
        sourcePath: path,
        sourceDigest: digest,
        evidenceKind: "manifest-declaration",
      });
    }
    const scriptNames = Object.keys(scripts ?? {}).sort(compareText);
    state.configurations.push({
      kind: "package-json",
      path,
      digest,
      parsed: true,
      signals: [
        `dependencies:${state.dependencies.filter(item => item.sourcePath === path).length}`,
        `node-runtime-declaration:${nodeVersion ?? "none-or-nonexact"}`,
        `scripts-declared-not-executed:${scriptNames.join(",") || "none"}`,
      ],
    });
    return true;
  } catch (error) {
    if (error instanceof MiniappInventoryError) throw error;
    const message = error instanceof Error ? error.message.slice(0, 256) : "invalid JSON";
    state.configurations.push({ kind: "package-json", path, digest, parsed: false, signals: [], error: message });
    state.configErrors.push({ path, message });
    return false;
  }
}

function parsePackageLock(path: string, digest: string, text: string, state: MutableScanState): boolean {
  try {
    const value = JSON.parse(text) as unknown;
    scanStructuredSecretValues(value, path);
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("root must be an object");
    const packages = (value as Readonly<Record<string, unknown>>).packages;
    if (!packages || typeof packages !== "object" || Array.isArray(packages)) throw new Error("packages map is required");
    for (const [packagePath, rawEntry] of Object.entries(packages as Readonly<Record<string, unknown>>)) {
      if (!packagePath.startsWith("node_modules/") || packagePath.slice("node_modules/".length).includes("/node_modules/")) continue;
      if (!rawEntry || typeof rawEntry !== "object" || Array.isArray(rawEntry)) continue;
      const version = (rawEntry as Readonly<Record<string, unknown>>).version;
      if (typeof version !== "string" || !/^[0-9]+(?:\.[0-9]+){1,3}(?:-[0-9A-Za-z.-]+)?$/u.test(version)) continue;
      const name = packagePath.slice("node_modules/".length);
      if (name) state.lockedDependencies.push({ name, version, sourcePath: path, sourceDigest: digest, packageManager: "npm" });
    }
    state.configurations.push({
      kind: "package-lock",
      path,
      digest,
      parsed: true,
      signals: [`locked-dependencies:${state.lockedDependencies.filter(item => item.sourcePath === path).length}`],
    });
    return true;
  } catch (error) {
    if (error instanceof MiniappInventoryError) throw error;
    const message = error instanceof Error ? error.message.slice(0, 256) : "invalid package lock";
    state.configurations.push({ kind: "package-lock", path, digest, parsed: false, signals: [], error: message });
    state.configErrors.push({ path, message });
    return false;
  }
}

function yamlScalar(value: string): string {
  const trimmed = value.trim();
  if ((trimmed.startsWith("'") && trimmed.endsWith("'")) || (trimmed.startsWith('"') && trimmed.endsWith('"'))) {
    return trimmed.slice(1, -1).replaceAll("''", "'");
  }
  return trimmed;
}

function parsePnpmLock(path: string, digest: string, text: string, state: MutableScanState): boolean {
  try {
    const lines = text.split(/\r?\n/u);
    if (!/^lockfileVersion:\s*['"]?9(?:\.0)?['"]?\s*$/u.test(lines[0] ?? "")) {
      throw new Error("lockfileVersion 9 is required");
    }
    let inImporter = false;
    let scope: "direct" | "dev" | null = null;
    let currentName: string | null = null;
    let currentVersion: string | null = null;
    const flush = (): void => {
      if (currentName && currentVersion && /^[0-9]+(?:\.[0-9]+){1,3}(?:-[0-9A-Za-z.-]+)?$/u.test(currentVersion)) {
        state.lockedDependencies.push({
          name: currentName,
          version: currentVersion,
          sourcePath: path,
          sourceDigest: digest,
          packageManager: "pnpm",
        });
      }
      currentName = null;
      currentVersion = null;
    };
    for (const line of lines) {
      if (/^importers:\s*$/u.test(line)) {
        flush();
        inImporter = false;
        scope = null;
        continue;
      }
      if (!inImporter && /^  \.\s*:\s*$/u.test(line)) {
        inImporter = true;
        scope = null;
        continue;
      }
      if (inImporter && /^  [^\s].*:\s*$/u.test(line)) {
        flush();
        inImporter = false;
        scope = null;
        continue;
      }
      if (!inImporter) continue;
      const scopeMatch = /^    (dependencies|devDependencies|optionalDependencies|peerDependencies):\s*$/u.exec(line);
      if (scopeMatch) {
        flush();
        scope = scopeMatch[1] === "devDependencies" ? "dev" : "direct";
        continue;
      }
      if (scope === null) continue;
      const dependencyMatch = /^      (['"]?)([^:'"]+)\1:\s*$/u.exec(line);
      if (dependencyMatch) {
        flush();
        currentName = yamlScalar(dependencyMatch[2]!);
        continue;
      }
      const versionMatch = /^        version:\s*(\S+)\s*$/u.exec(line);
      if (versionMatch && currentName) {
        const version = yamlScalar(versionMatch[1]!);
        currentVersion = version.split("(")[0] ?? version;
      }
    }
    flush();
    const count = state.lockedDependencies.filter(item => item.sourcePath === path).length;
    if (count === 0) throw new Error("root importer has no resolved dependencies");
    state.configurations.push({
      kind: "pnpm-lock",
      path,
      digest,
      parsed: true,
      signals: [`locked-dependencies:${count}`],
    });
    return true;
  } catch (error) {
    if (error instanceof MiniappInventoryError) throw error;
    const message = error instanceof Error ? error.message.slice(0, 256) : "invalid pnpm lock";
    state.configurations.push({ kind: "pnpm-lock", path, digest, parsed: false, signals: [], error: message });
    state.configErrors.push({ path, message });
    return false;
  }
}

function parsePubspec(path: string, digest: string, text: string, state: MutableScanState): boolean {
  try {
    const lines = text.split(/\r?\n/u);
    let scope: "direct" | "dev" | null = null;
    let sawFlutter = false;
    for (const line of lines) {
      if (/^dependencies:\s*(?:#.*)?$/u.test(line)) scope = "direct";
      else if (/^dev_dependencies:\s*(?:#.*)?$/u.test(line)) scope = "dev";
      else if (/^[^\s#][^:]*:/u.test(line)) scope = null;
      const dependency = /^  ([A-Za-z0-9_-]+):(?:\s*([^#\s][^#]*?)\s*)?(?:#.*)?$/u.exec(line);
      if (scope && dependency) {
        const name = dependency[1]!;
        const version = dependency[2]?.trim() || "declared-map";
        state.dependencies.push({ name, version, scope, sourcePath: path });
        if (name === "flutter") sawFlutter = true;
      }
      if (/\bsdk:\s*flutter\b/u.test(line)) sawFlutter = true;
    }
    if (sawFlutter) addSignal(state, "flutter", "manifest-dependency", path, "Flutter SDK declared", 0.96);
    state.configurations.push({
      kind: "pubspec",
      path,
      digest,
      parsed: true,
      signals: [
        `dependencies:${state.dependencies.filter(item => item.sourcePath === path).length}`,
        `flutter-sdk:${sawFlutter ? "declared" : "not-declared"}`,
      ],
    });
    return true;
  } catch (error) {
    if (error instanceof MiniappInventoryError) throw error;
    const message = error instanceof Error ? error.message.slice(0, 256) : "invalid pubspec";
    state.configurations.push({ kind: "pubspec", path, digest, parsed: false, signals: [], error: message });
    state.configErrors.push({ path, message });
    return false;
  }
}

function parseAppConfig(path: string, digest: string, text: string, state: MutableScanState): boolean {
  try {
    const value = JSON.parse(text) as unknown;
    scanStructuredSecretValues(value, path);
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("root must be an object");
    const keys = Object.keys(value as Readonly<Record<string, unknown>>).sort(compareText);
    const name = baseName(path);
    if (name === "pages.json" || name === "manifest.json") {
      addSignal(state, "uni-app", "platform-config", path, `${name} present`, name === "pages.json" ? 0.76 : 0.55);
    } else {
      addSignal(state, "native-miniapp", "platform-config", path, `${name} present`, name === "app.json" ? 0.88 : 0.68);
    }
    state.configurations.push({ kind: "app-config", path, digest, parsed: true, signals: keys.map(key => `key:${key}`) });
    return true;
  } catch (error) {
    if (error instanceof MiniappInventoryError) throw error;
    const message = error instanceof Error ? error.message.slice(0, 256) : "invalid JSON";
    state.configurations.push({ kind: "app-config", path, digest, parsed: false, signals: [], error: message });
    state.configErrors.push({ path, message });
    return false;
  }
}

function collectPathSignals(path: string, text: string | null, state: MutableScanState): void {
  const extension = fileExtension(path);
  const name = baseName(path);
  if (name === "tsconfig.json") addSignal(state, "typescript", "language-config", path, "tsconfig.json present", 0.84);
  if (extension === ".ts" || extension === ".tsx" || extension === ".mts" || extension === ".cts") {
    addSignal(state, "typescript", "file-extension", path, extension, 0.2);
  }
  if (extension === ".js" || extension === ".jsx" || extension === ".mjs" || extension === ".cjs") {
    addSignal(state, "javascript", "file-extension", path, extension, 0.16);
  }
  if (extension === ".vue") {
    addSignal(state, "vue2", "file-extension", path, ".vue single-file component", 0.3);
    addSignal(state, "vue3", "file-extension", path, ".vue single-file component", 0.3);
  }
  if (extension === ".tsx" || extension === ".jsx") {
    addSignal(state, "react", "file-extension", path, `${extension} component candidate`, 0.26);
  }
  if (extension === ".dart") addSignal(state, "flutter", "file-extension", path, ".dart source", 0.38);
  if (extension === ".html" || extension === ".htm") addSignal(state, "h5", "file-extension", path, extension, 0.68);
  if (miniappTemplateExtensions.has(extension)) {
    addSignal(state, "native-miniapp", "file-extension", path, `${extension} native template`, 0.62);
  }
  if (name === "pages.json") addSignal(state, "uni-app", "platform-config", path, "pages.json present", 0.76);
  if (/^(?:main|index|app)\.(?:[cm]?[jt]sx?|vue|dart)$/u.test(name) || path === "lib/main.dart") {
    state.entrypoints.add(path);
  }
  if (/(?:^|\/)(?:router|routes?)(?:\/|\.)/iu.test(path) || name === "pages.json" || name === "app.json") {
    state.routes.add(path);
  }
  if (extension === ".vue" || extension === ".tsx" || extension === ".jsx" || /(?:^|\/)components?\//iu.test(path)) {
    state.components.add(path);
  }
  if (/(?:^|\/)(?:store|stores|redux|pinia)(?:\/|\.)/iu.test(path)) state.stores.add(path);
  if (assetExtensions.has(extension)) state.assets.add(path);
  if (!text) return;
  if (/\bfrom\s+["']react["']|\brequire\(["']react["']\)|\bReact\./u.test(text)) {
    addSignal(state, "react", "source-import", path, "React import or namespace", 0.45);
  }
  if (/\bfrom\s+["']vue["']|\brequire\(["']vue["']\)/u.test(text)) {
    addSignal(state, "vue3", "source-import", path, "Vue import with unresolved major", 0.3);
    addSignal(state, "vue2", "source-import", path, "Vue import with unresolved major", 0.3);
  }
  if (/[@"']tarojs\//u.test(text)) addSignal(state, "taro", "source-import", path, "@tarojs import", 0.78);
  if (/@dcloudio\/|\buni\./u.test(text)) addSignal(state, "uni-app", "source-import", path, "uni-app import or API", 0.72);
  const platformPatterns = [
    ["wechat", /\bwx\s*\./u],
    ["alipay", /\bmy\s*\./u],
    ["douyin", /\btt\s*\./u],
    ["baidu", /\bswan\s*\./u],
    ["xiaohongshu", /\bxhs\s*\./u],
  ] as const;
  for (const [platform, pattern] of platformPatterns) {
    if (pattern.test(text)) state.platformApiSignals.add(`${platform}:${path}`);
  }
}

function confidence(signals: readonly MiniappFrameworkSignal[]): number {
  const remaining = signals.reduce((product, signal) => product * (1 - signal.weight), 1);
  return Math.round(Math.min(0.999, 1 - remaining) * 1000) / 1000;
}

function candidates(state: MutableScanState): readonly MiniappFrameworkCandidate[] {
  const labelIndex = new Map(MINIAPP_SOURCE_LABELS.map((label, index) => [label, index]));
  return [...state.signals.entries()].map(([sourceLabel, rawSignals]) => {
    const evidence = [...rawSignals].sort((left, right) => compareText(
      `${left.path}\u0000${left.kind}\u0000${left.detail}`,
      `${right.path}\u0000${right.kind}\u0000${right.detail}`,
    ));
    return { sourceLabel, confidence: confidence(evidence), evidence };
  }).sort((left, right) => right.confidence - left.confidence
    || (labelIndex.get(left.sourceLabel) ?? 99) - (labelIndex.get(right.sourceLabel) ?? 99));
}

function isLanguage(label: MiniappSourceLabel): boolean {
  return label === "typescript" || label === "javascript";
}

function expectedLayering(left: MiniappSourceLabel, right: MiniappSourceLabel): boolean {
  if (isLanguage(left) || isLanguage(right)) return true;
  const pair = new Set([left, right]);
  if (pair.has("h5") && (pair.has("react") || pair.has("vue2") || pair.has("vue3"))) return true;
  if (pair.has("taro") && (pair.has("react") || pair.has("vue2") || pair.has("vue3") || pair.has("h5"))) return true;
  if (pair.has("uni-app") && (pair.has("vue2") || pair.has("vue3") || pair.has("h5"))) return true;
  return false;
}

function conflicts(found: readonly MiniappFrameworkCandidate[]): readonly MiniappFrameworkConflict[] {
  const strong = found.filter(candidate => candidate.confidence >= 0.75 && !isLanguage(candidate.sourceLabel));
  const output: MiniappFrameworkConflict[] = [];
  for (let leftIndex = 0; leftIndex < strong.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < strong.length; rightIndex += 1) {
      const left = strong[leftIndex]!;
      const right = strong[rightIndex]!;
      const vuePair = new Set([left.sourceLabel, right.sourceLabel]);
      if (vuePair.size === 2 && vuePair.has("vue2") && vuePair.has("vue3")) {
        const exactMajorEvidence = [...left.evidence, ...right.evidence].some(signal =>
          signal.kind === "manifest-dependency"
          && signal.detail.startsWith("vue@")
          && vueMajor(signal.detail) !== null);
        if (exactMajorEvidence) continue;
      }
      if (!expectedLayering(left.sourceLabel, right.sourceLabel)) {
        const sourceLabels = [left.sourceLabel, right.sourceLabel].sort((a, b) => compareText(a, b));
        output.push({
          sourceLabels,
          reason: `independent strong source signals for ${sourceLabels.join(" and ")}`,
          blocking: true,
        });
      }
    }
  }
  return output.sort((left, right) => compareText(left.sourceLabels.join("\u0000"), right.sourceLabels.join("\u0000")));
}

function selectedLabel(
  hint: MiniappSourceLabel | "auto",
  found: readonly MiniappFrameworkCandidate[],
  foundConflicts: readonly MiniappFrameworkConflict[],
): MiniappSourceLabel | null {
  if (foundConflicts.length > 0) return null;
  if (hint !== "auto") {
    return (found.find(candidate => candidate.sourceLabel === hint)?.confidence ?? 0) >= 0.5 ? hint : null;
  }
  const byLabel = new Map(found.map(candidate => [candidate.sourceLabel, candidate]));
  return selectionOrder.find(label => (byLabel.get(label)?.confidence ?? 0) >= 0.8) ?? null;
}

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") {
    const candidate = value as Readonly<Record<string, unknown>>;
    return Object.fromEntries(Object.keys(candidate).sort(compareText).map(key => [key, canonicalValue(candidate[key])]));
  }
  return value;
}

export function canonicalizeMiniappSourceInventory(inventory: MiniappSourceInventory): string {
  return JSON.stringify(canonicalValue(inventory));
}

export function inventoryMiniappSource(value: unknown): MiniappSourceInventory {
  const input = validateMiniappInventoryInput(value);
  const state: MutableScanState = {
    signals: new Map(),
    dependencies: [],
    lockedDependencies: [],
    declaredRuntimes: [],
    configurations: [],
    entrypoints: new Set(),
    routes: new Set(),
    components: new Set(),
    stores: new Set(),
    assets: new Set(),
    platformApiSignals: new Set(),
    configErrors: [],
  };
  const files: MiniappInventoryFile[] = [];
  for (const inputFile of input.files) {
    const content = bytes(inputFile.content);
    const digest = sha256(content);
    const text = decodeText(content);
    if (text !== null) assertNoUnsafeSecrets(inputFile.path, text);
    collectPathSignals(inputFile.path, text, state);
    let parsed = true;
    const name = baseName(inputFile.path);
    if (text !== null && name === "package.json") parsed = parsePackageJson(inputFile.path, digest, text, state);
    else if (text !== null && name === "package-lock.json") parsed = parsePackageLock(inputFile.path, digest, text, state);
    else if (text !== null && name === "pnpm-lock.yaml") parsed = parsePnpmLock(inputFile.path, digest, text, state);
    else if (text !== null && name === "pubspec.yaml") parsed = parsePubspec(inputFile.path, digest, text, state);
    else if (text !== null && appConfigNames.has(name)) parsed = parseAppConfig(inputFile.path, digest, text, state);
    const kind = fileKind(inputFile.path, text === null);
    files.push(parsed ? {
      path: inputFile.path,
      digest,
      byteCount: content.byteLength,
      kind,
      status: text === null ? "binary" : "eligible",
    } : {
      path: inputFile.path,
      digest,
      byteCount: content.byteLength,
      kind,
      status: "parse-error",
      reason: "configuration parse failed",
    });
  }
  const frameworkCandidates = candidates(state);
  const frameworkConflicts = conflicts(frameworkCandidates);
  const selectedSourceLabel = selectedLabel(input.sourceLabelHint, frameworkCandidates, frameworkConflicts);
  const findings: MiniappInventoryFinding[] = [];
  if (frameworkCandidates.length === 0 || !frameworkCandidates.some(candidate => candidate.confidence >= 0.5)) {
    findings.push({
      code: "MINIAPP_FRAMEWORK_NOT_DETECTED",
      severity: "ERROR",
      message: "No source label has sufficient independent evidence.",
      paths: [],
      blocking: true,
    });
  }
  if (frameworkConflicts.length > 0) {
    findings.push({
      code: "MINIAPP_FRAMEWORK_CONFLICT",
      severity: "ERROR",
      message: "Multiple incompatible strong source-framework candidates require an explicit boundary decision.",
      paths: [...new Set(frameworkConflicts.flatMap(conflict => conflict.sourceLabels.flatMap(label =>
        frameworkCandidates.find(candidate => candidate.sourceLabel === label)?.evidence.map(item => item.path) ?? [])))].sort(compareText),
      blocking: true,
    });
  }
  if (input.sourceLabelHint !== "auto"
    && (frameworkCandidates.find(candidate => candidate.sourceLabel === input.sourceLabelHint)?.confidence ?? 0) < 0.5) {
    findings.push({
      code: "MINIAPP_FRAMEWORK_HINT_MISMATCH",
      severity: "ERROR",
      message: `The requested ${input.sourceLabelHint} hint is not supported by the scanned evidence.`,
      paths: [],
      blocking: true,
    });
  }
  for (const error of state.configErrors.sort((left, right) => compareText(left.path, right.path))) {
    findings.push({
      code: "MINIAPP_CONFIG_PARSE_ERROR",
      severity: "ERROR",
      message: `${error.path}: ${error.message}`,
      paths: [error.path],
      blocking: true,
    });
  }
  const unsupportedSourcePaths = files.filter(file => unsupportedSourceExtensions.has(fileExtension(file.path))).map(file => file.path).sort(compareText);
  if (unsupportedSourcePaths.length > 0) {
    findings.push({
      code: "MINIAPP_SOURCE_FILE_UNSUPPORTED",
      severity: "ERROR",
      message: `Unsupported source-language files require an exact parser or an explicit exclusion contract: ${unsupportedSourcePaths.join(", ")}`,
      paths: unsupportedSourcePaths,
      blocking: true,
    });
  }
  const unclassifiedSourcePaths = files.filter(file => file.status === "eligible"
    && file.kind === "text"
    && !explicitlyNonRuntimeText(file.path)
    && !unsupportedSourceExtensions.has(fileExtension(file.path)))
    .map(file => file.path)
    .sort(compareText);
  if (unclassifiedSourcePaths.length > 0) {
    findings.push({
      code: "MINIAPP_SOURCE_FILE_UNCLASSIFIED",
      severity: "ERROR",
      message: `Eligible text files require a parser, typed asset/data contract, or explicit non-runtime classification: ${unclassifiedSourcePaths.join(", ")}`,
      paths: unclassifiedSourcePaths,
      blocking: true,
    });
  }
  const configurationEvidence = [...state.configurations].sort((left, right) => compareText(
    `${left.path}\u0000${left.kind}`,
    `${right.path}\u0000${right.kind}`,
  ));
  const eligibleFiles = files.filter(file => file.status === "eligible").length;
  const fileSetDigest = sha256(files.map(file => `${file.path}\u0000${file.digest}\u0000${file.byteCount}`).join("\n"));
  return {
    schemaVersion: "1.0",
    inventoryId: input.inventoryId,
    sourceRevision: input.sourceRevision,
    sourceSnapshotDigest: input.sourceSnapshotDigest,
    fileSetDigest,
    files,
    frameworkCandidates,
    selectedSourceLabel,
    frameworkConflicts,
    dependencies: [...state.dependencies].sort((left, right) => compareText(
      `${left.sourcePath}\u0000${left.scope}\u0000${left.name}\u0000${left.version}`,
      `${right.sourcePath}\u0000${right.scope}\u0000${right.name}\u0000${right.version}`,
    )),
    lockedDependencies: [...state.lockedDependencies].sort((left, right) => compareText(
      `${left.sourcePath}\u0000${left.name}\u0000${left.version}`,
      `${right.sourcePath}\u0000${right.name}\u0000${right.version}`,
    )),
    declaredRuntimes: [...state.declaredRuntimes].sort((left, right) => compareText(
      `${left.sourcePath}\u0000${left.runtime}\u0000${left.version}`,
      `${right.sourcePath}\u0000${right.runtime}\u0000${right.version}`,
    )),
    configurationEvidence,
    entrypoints: [...state.entrypoints].sort(compareText),
    routes: [...state.routes].sort(compareText),
    components: [...state.components].sort(compareText),
    stores: [...state.stores].sort(compareText),
    assets: [...state.assets].sort(compareText),
    platformApiSignals: [...state.platformApiSignals].sort(compareText),
    coverage: {
      totalFiles: files.length,
      eligibleFiles,
      processedFiles: files.length,
      configurationFiles: configurationEvidence.length,
      parsedConfigurationFiles: configurationEvidence.filter(item => item.parsed).length,
      ratio: 1,
    },
    findings,
  };
}
