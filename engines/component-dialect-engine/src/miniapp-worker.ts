/**
 * Controlled stdin/stdout JSON worker for frontend/native-miniapp analysis
 * and native mini-app emission.
 *
 * The protocol is intentionally closed.  Unknown actions, frameworks,
 * platforms, fields and nested source fields are rejected before parsing.
 * No input path is opened and no generated file is written by this worker.
 */
import { createHash } from "crypto";
import * as fs from "fs";
import * as path from "path";
import * as ts from "typescript";
import { TextDecoder } from "util";
import {
  ComponentDef,
  DialectError,
  Expr,
  ListElementShape,
  ListPropDef,
  Node as CanonicalNode,
  PrimitiveType,
  validateComponent,
} from "./models";
import { emitPlatformMiniApp, MiniAppPlatform, MINI_APP_PLATFORMS } from "./emitters/platform-miniapps";
import { referencedComponents } from "./emitters/react";
import { parseMiniProgramComponent, MiniProgramSource } from "./parsers/miniprogram";
import { parseReactComponent } from "./parsers/react";
import { parseVue2Component } from "./parsers/vue2";
import { parseVue3Component } from "./parsers/vue3";

export const MINI_APP_SOURCE_FRAMEWORKS = [
  "react",
  "typescript",
  "react-native",
  "vue2",
  "vue3",
  "miniprogram",
] as const;
export type MiniAppSourceFramework = (typeof MINI_APP_SOURCE_FRAMEWORKS)[number];

export interface MiniAppSourceParserProfile {
  readonly sourceFrameworkVersion: string;
  readonly sourceLanguageVersion: string;
  readonly parser: string;
  readonly parserVersion: string;
  readonly expressionParser: string | null;
  readonly expressionParserVersion: string | null;
  readonly semanticAdapter: string;
  readonly semanticStatus: "IMPLEMENTED" | "BLOCKED";
}

/**
 * Exact parser bindings installed by this package.  A syntactically capable
 * parser is not automatically a semantic adapter: React Native is listed so
 * its one known request tuple can fail with the precise semantic blocker,
 * never fall through the web JSX adapter.
 */
export const MINI_APP_SOURCE_PARSER_PROFILES = {
  react: {
    sourceFrameworkVersion: "18.3.1",
    sourceLanguageVersion: "5.9.2",
    parser: "typescript",
    parserVersion: "5.9.2",
    expressionParser: null,
    expressionParserVersion: null,
    semanticAdapter: "react-component-v1",
    semanticStatus: "IMPLEMENTED",
  },
  typescript: {
    sourceFrameworkVersion: "5.9.2",
    sourceLanguageVersion: "5.9.2",
    parser: "typescript",
    parserVersion: "5.9.2",
    expressionParser: null,
    expressionParserVersion: null,
    semanticAdapter: "typescript-jsx-component-v1",
    semanticStatus: "IMPLEMENTED",
  },
  "react-native": {
    sourceFrameworkVersion: "0.76.5",
    sourceLanguageVersion: "5.9.2",
    parser: "typescript",
    parserVersion: "5.9.2",
    expressionParser: null,
    expressionParserVersion: null,
    semanticAdapter: "react-native-component-v1",
    semanticStatus: "BLOCKED",
  },
  vue2: {
    sourceFrameworkVersion: "2.7.16",
    sourceLanguageVersion: "5.9.2",
    parser: "vue-template-compiler/build",
    parserVersion: "2.7.16",
    expressionParser: "typescript",
    expressionParserVersion: "5.9.2",
    semanticAdapter: "vue2-component-v1",
    semanticStatus: "IMPLEMENTED",
  },
  vue3: {
    sourceFrameworkVersion: "3.5.13",
    sourceLanguageVersion: "5.9.2",
    parser: "@vue/compiler-sfc",
    parserVersion: "3.5.13",
    expressionParser: "typescript",
    expressionParserVersion: "5.9.2",
    semanticAdapter: "vue3-component-v1",
    semanticStatus: "IMPLEMENTED",
  },
  miniprogram: {
    sourceFrameworkVersion: "0.4.0",
    sourceLanguageVersion: "5.9.2",
    parser: "@wxml/parser",
    parserVersion: "0.4.0",
    expressionParser: "typescript",
    expressionParserVersion: "5.9.2",
    semanticAdapter: "wechat-component-v1",
    semanticStatus: "IMPLEMENTED",
  },
} as const satisfies Readonly<Record<MiniAppSourceFramework, MiniAppSourceParserProfile>>;

export interface MiniAppTargetGeneratorProfile {
  readonly platformVersion: string;
  readonly toolchainVersion: string;
  readonly profileVersion: string;
  readonly generator: "component-dialect-engine/platform-miniapps";
  readonly generatorVersion: "0.1.0";
  readonly canonicalProfile: "certified-component-v1";
}

/**
 * Only generator tuples also admitted by the repository MiniApp planner are
 * exposed here.  Douyin and Xiaohongshu renderers remain directly unit-testable
 * implementation candidates, but have no exact toolchain tuple and therefore
 * cannot be requested through this evidence-bearing worker.
 */
export const MINI_APP_TARGET_GENERATOR_PROFILES = {
  wechat: {
    platformVersion: "3.9.1",
    toolchainVersion: "1.06.2504010",
    profileVersion: "2026-08-20.1",
    generator: "component-dialect-engine/platform-miniapps",
    generatorVersion: "0.1.0",
    canonicalProfile: "certified-component-v1",
  },
  alipay: {
    platformVersion: "2.10.2",
    toolchainVersion: "3.9.4",
    profileVersion: "2026-08-20.1",
    generator: "component-dialect-engine/platform-miniapps",
    generatorVersion: "0.1.0",
    canonicalProfile: "certified-component-v1",
  },
} as const satisfies Readonly<Partial<Record<MiniAppPlatform, MiniAppTargetGeneratorProfile>>>;

const MAX_STDIN_BYTES = 2 * 1024 * 1024;
const MAX_SOURCE_BYTES = 1024 * 1024;
const SAFE_FILE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SAFE_COMPONENT_NAME = /^[A-Z][A-Za-z0-9]{0,127}$/;
const SHA256_DIGEST = /^sha256:[a-f0-9]{64}$/;
const SAFE_SECRET_REFERENCE = /^(?:kms|secret|vault):\/\/[A-Za-z0-9][A-Za-z0-9._/@:-]{0,511}$/u;
const SENSITIVE_BINDING_SUFFIX = /(?:secret|token|password|passwd|credential|credentials|privatekey|apikey|accesskey|accesskeyid|authorization|cookie|session|sessionid|sessionkey)(?:value|material)?$/u;

const SECRET_MATERIAL_RULES: readonly {
  readonly id: string;
  readonly pattern: RegExp;
}[] = [
  { id: "private-key-pem", pattern: /-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----/u },
  { id: "aws-access-key", pattern: /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/u },
  { id: "github-token", pattern: /\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{36,255}\b/u },
  { id: "stripe-live-secret", pattern: /\bsk_live_[A-Za-z0-9]{16,255}\b/u },
  {
    id: "jwt",
    pattern: /\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{3,}\b/u,
  },
  {
    id: "authorization-token",
    pattern: /\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/-]{16,}={0,2}(?![A-Za-z0-9._~+/=-])/iu,
  },
  {
    id: "literal-credential-assignment",
    pattern: /\b(?:api[_-]?key|apiKey|app[_-]?secret|appSecret|client[_-]?secret|clientSecret|access[_-]?token|accessToken|auth[_-]?token|authToken|session[_-]?token|sessionToken|refresh[_-]?token|refreshToken|id[_-]?token|idToken|authorization|private[_-]?key|privateKey|credential|credentials|cookie|set[_-]?cookie|setCookie|password|passwd)\b\s*[:=]\s*["'`](?!(?:kms|secret|vault):\/\/)[^"'`\r\n]{8,}["'`]/iu,
  },
  {
    id: "sensitive-http-header",
    pattern: /\b(?:authorization|cookie|set-cookie|x-api-key)\s*:\s*(?:Token\s+)?[A-Za-z0-9._~+\/=;-]{8,}/iu,
  },
  { id: "credential-url", pattern: /\bhttps?:\/\/[^\s/:@]+:[^\s/@]+@/iu },
];

type NoteStatus = "INFORMATIONAL" | "NOT_RUN" | "NOT_CERTIFIED";

export interface MiniAppWorkerNote {
  code: string;
  category: "semantic" | "evidence-boundary";
  status: NoteStatus;
  message: string;
}

export interface MiniAppWorkerEvidence {
  requestValidation: "PASSED" | "BLOCKED" | "NOT_RUN";
  sourceParse: "PASSED" | "BLOCKED" | "NOT_RUN";
  canonicalValidation: "PASSED" | "BLOCKED" | "NOT_RUN";
  localEmission: "PASSED" | "BLOCKED" | "NOT_RUN";
  externalPlatformBuild: "NOT_RUN";
  externalPlatformRuntime: "NOT_RUN";
  certification: "NOT_CERTIFIED";
}

export interface MiniAppComponentRegistryEntry {
  readonly name: string;
  readonly source: string | MiniProgramSource;
  readonly fileName: string;
  readonly canonicalComponentDigest: string;
}

export interface MiniAppWorkerProvenance {
  /** SHA-256 of exact source bytes, or a labelled binary frame for {wxml,js}. */
  readonly rawSourceSha256: string;
  /** Source payload bytes only; the native-bundle digest framing is excluded. */
  readonly rawSourceBytes: number;
  /** Canonical digest of the validated request, including its source payload. */
  readonly requestDigest: string;
  /** Digest binding request, raw source identity, parser and emitter profiles. */
  readonly inputDigest: string;
  readonly parserProfileDigest: string;
  readonly emitterProfileDigest: string | null;
  readonly generatedFilesDigest: string | null;
  /** Direct parser entries/package metadata plus engine package/lock bytes. */
  readonly dependencyEvidenceLevel: "DIRECT_ENTRIES_METADATA_AND_ENGINE_LOCKS";
}

interface SourceBoundRequest {
  sourceFramework: MiniAppSourceFramework;
  sourceFrameworkVersion: string;
  sourceLanguageVersion: string;
  source: string | MiniProgramSource;
  fileName: string;
}

interface AnalyzeRequest extends SourceBoundRequest {
  action: "analyze";
}

interface EmitRequest extends SourceBoundRequest {
  action: "emit";
  targetPlatform: MiniAppPlatform;
  platformVersion: string;
  toolchainVersion: string;
  profileVersion: string;
  componentRegistry: readonly MiniAppComponentRegistryEntry[];
}

export type MiniAppWorkerRequest = AnalyzeRequest | EmitRequest;

export interface MiniAppAnalyzeResponse {
  ok: true;
  action: "analyze";
  sourceFramework: MiniAppSourceFramework;
  sourceFrameworkVersion: string;
  sourceLanguageVersion: string;
  component: ComponentDef;
  canonicalComponentDigest: string;
  provenance: MiniAppWorkerProvenance;
  notes: MiniAppWorkerNote[];
  evidence: MiniAppWorkerEvidence;
}

export interface MiniAppEmittedChildBundle {
  readonly component: ComponentDef;
  readonly canonicalComponentDigest: string;
  readonly files: Readonly<Record<string, string>>;
  readonly fileIdentities: Readonly<Record<string, MiniAppGeneratedFileIdentity>>;
  readonly bundleDigest: string;
  readonly bundleBytes: number;
}

export interface MiniAppGeneratedFileIdentity {
  readonly sha256: string;
  readonly bytes: number;
}

export interface MiniAppEmitResponse {
  ok: true;
  action: "emit";
  sourceFramework: MiniAppSourceFramework;
  sourceFrameworkVersion: string;
  sourceLanguageVersion: string;
  targetPlatform: MiniAppPlatform;
  platformVersion: string;
  toolchainVersion: string;
  profileVersion: string;
  component: ComponentDef;
  canonicalComponentDigest: string;
  provenance: MiniAppWorkerProvenance;
  files: Readonly<Record<string, string>>;
  readonly fileIdentities: Readonly<Record<string, MiniAppGeneratedFileIdentity>>;
  /** Every transitive child referenced by the parent, emitted in this request. */
  childBundles: Readonly<Record<string, MiniAppEmittedChildBundle>>;
  templateExtension: "wxml" | "axml" | "ttml" | "xhsml";
  styleExtension: "wxss" | "acss" | "ttss" | "css";
  notes: MiniAppWorkerNote[];
  evidence: MiniAppWorkerEvidence;
}

export interface MiniAppErrorResponse {
  ok: false;
  error: {
    code: string;
    message: string;
  };
  /** Present only after the request passed its exact schema/tuple boundary. */
  provenance: MiniAppWorkerProvenance | null;
  notes: MiniAppWorkerNote[];
  evidence: MiniAppWorkerEvidence;
}

export type MiniAppWorkerResponse = MiniAppAnalyzeResponse | MiniAppEmitResponse;

type MiniAppWorkerStage =
  | "request-validation"
  | "source-parse"
  | "canonical-validation"
  | "local-emission";

export class MiniAppWorkerError extends Error {
  readonly code: string;
  readonly reason: string;
  readonly stage: MiniAppWorkerStage;
  readonly provenance: MiniAppWorkerProvenance | null;

  constructor(
    code: string,
    reason: string,
    stage: MiniAppWorkerStage = "request-validation",
    provenance: MiniAppWorkerProvenance | null = null,
  ) {
    super(`${code}: ${reason}`);
    this.name = "MiniAppWorkerError";
    this.code = code;
    this.reason = reason;
    this.stage = stage;
    this.provenance = provenance;
  }
}

function block(
  code: string,
  message: string,
  stage: MiniAppWorkerStage = "request-validation",
): never {
  throw new MiniAppWorkerError(code, message, stage);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function exactKeys(object: Record<string, unknown>, expected: readonly string[], what: string): void {
  const actual = Object.keys(object).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    block("MINIAPP_WORKER_SCHEMA_VIOLATION", `${what} fields must be exactly ${JSON.stringify(wanted)}; received ${JSON.stringify(actual)}`);
  }
}

function requiredString(object: Record<string, unknown>, key: string): string {
  const value = object[key];
  if (typeof value !== "string") block("MINIAPP_WORKER_SCHEMA_VIOLATION", `${key} must be a string`);
  return value as string;
}

function assertNoSecretMaterial(
  value: string,
  location: string,
  stage: MiniAppWorkerStage,
): void {
  for (const rule of SECRET_MATERIAL_RULES) {
    if (rule.pattern.test(value)) {
      block(
        stage === "local-emission"
          ? "MINIAPP_WORKER_GENERATED_SECRET_MATERIAL"
          : "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
        `${location} matched secret-material rule ${rule.id}; the matched value is intentionally not reported`,
        stage,
      );
    }
  }
}

function normalizedSensitiveName(value: string): string {
  return value.normalize("NFKC").replace(/[^A-Za-z0-9]/gu, "").toLowerCase();
}

function isSensitiveName(value: string): boolean {
  return SENSITIVE_BINDING_SUFFIX.test(normalizedSensitiveName(value));
}

function staticStringExpression(expression: ts.Expression): string | null {
  if (ts.isStringLiteralLike(expression)) return expression.text;
  if (ts.isParenthesizedExpression(expression)) {
    return staticStringExpression(expression.expression);
  }
  if (
    ts.isBinaryExpression(expression) &&
    expression.operatorToken.kind === ts.SyntaxKind.PlusToken
  ) {
    const left = staticStringExpression(expression.left);
    const right = staticStringExpression(expression.right);
    if (left === null || right === null) return null;
    const combined = left + right;
    return combined.length <= 1024 ? combined : null;
  }
  return null;
}

function propertyNameText(name: ts.PropertyName): string | null {
  if (
    ts.isIdentifier(name) ||
    ts.isStringLiteralLike(name) ||
    ts.isNumericLiteral(name)
  ) {
    return name.text;
  }
  if (ts.isComputedPropertyName(name)) return staticStringExpression(name.expression);
  return null;
}

function assignedExpressionName(expression: ts.Expression): string | null {
  if (ts.isIdentifier(expression)) return expression.text;
  if (ts.isPropertyAccessExpression(expression)) return expression.name.text;
  if (
    ts.isElementAccessExpression(expression) &&
    expression.argumentExpression !== undefined &&
    staticStringExpression(expression.argumentExpression) !== null
  ) {
    return staticStringExpression(expression.argumentExpression);
  }
  if (ts.isParenthesizedExpression(expression)) {
    return assignedExpressionName(expression.expression);
  }
  return null;
}

function bindingNames(name: ts.BindingName): readonly string[] {
  if (ts.isIdentifier(name)) return [name.text];
  return name.elements.flatMap((element) =>
    ts.isOmittedExpression(element) ? [] : bindingNames(element.name),
  );
}

function isExactAllowedSecretReference(expression: ts.Expression): boolean {
  return (
    ts.isStringLiteralLike(expression) &&
    SAFE_SECRET_REFERENCE.test(expression.text) &&
    !expression.text.includes("..")
  );
}

function blockUnsafeSensitiveBinding(
  name: string,
  expression: ts.Expression | undefined,
  location: string,
  stage: "request-validation" | "local-emission",
): void {
  if (expression !== undefined && isExactAllowedSecretReference(expression)) {
    return;
  }
  block(
    stage === "local-emission"
      ? "MINIAPP_WORKER_GENERATED_SECRET_MATERIAL"
      : "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
    `${location} assigns sensitive binding ${name}; only one literal vault://, secret://, or kms:// reference is allowed and the value is intentionally not reported`,
    stage,
  );
}

function blockUnresolvedComputedBinding(
  location: string,
  stage: "request-validation" | "local-emission",
): never {
  block(
    stage === "local-emission"
      ? "MINIAPP_WORKER_GENERATED_SECRET_MATERIAL"
      : "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
    `${location} uses a computed binding name that cannot be proven non-sensitive; dynamic binding names are outside this worker`,
    stage,
  );
}

function executableSourceUnits(
  source: string | MiniProgramSource,
  framework: MiniAppSourceFramework,
  label: string,
): readonly { readonly code: string; readonly label: string; readonly scriptKind: ts.ScriptKind }[] {
  if (typeof source !== "string") {
    return [{ code: source.js, label: `${label}.js`, scriptKind: ts.ScriptKind.JS }];
  }
  if (framework !== "vue2" && framework !== "vue3") {
    return [{ code: source, label, scriptKind: ts.ScriptKind.TSX }];
  }
  try {
    if (framework === "vue3") {
      const compiler = require("@vue/compiler-sfc") as {
        readonly parse: (
          input: string,
          options: { readonly filename: string },
        ) => {
          readonly errors: readonly unknown[];
          readonly descriptor: {
            readonly script?: { readonly content: string } | null;
            readonly scriptSetup?: { readonly content: string } | null;
          };
        };
      };
      const parsed = compiler.parse(source, { filename: label });
      if (parsed.errors.length > 0) {
        block(
          "MINIAPP_WORKER_SECRET_SCAN_PARSE_BLOCKED",
          `${label} could not be structurally segmented for secret scanning`,
        );
      }
      return [parsed.descriptor.script, parsed.descriptor.scriptSetup]
        .flatMap((script, index) => script === null || script === undefined
          ? []
          : [{
              code: script.content,
              label: `${label}.script[${index}]`,
              scriptKind: ts.ScriptKind.TSX,
            }]);
    }
    const compiler = require("vue-template-compiler/build") as {
      readonly parseComponent: (input: string) => {
        readonly script?: { readonly content: string } | null;
      };
    };
    const descriptor = compiler.parseComponent(source);
    return descriptor.script === null || descriptor.script === undefined
      ? []
      : [{
          code: descriptor.script.content,
          label: `${label}.script[0]`,
          scriptKind: ts.ScriptKind.TSX,
        }];
  } catch (error) {
    if (error instanceof MiniAppWorkerError) throw error;
    block(
      "MINIAPP_WORKER_SECRET_SCAN_PARSE_BLOCKED",
      `${label} could not be structurally segmented for secret scanning`,
    );
  }
}

function vue2TemplateBindingName(rawName: string): string | null {
  if (rawName.startsWith(":")) return rawName.slice(1);
  if (rawName.startsWith("v-bind:")) return rawName.slice("v-bind:".length);
  if (
    rawName.startsWith("@") ||
    rawName.startsWith("v-on:") ||
    rawName.startsWith("#") ||
    rawName.startsWith("v-slot:") ||
    rawName.startsWith("v-")
  ) {
    return null;
  }
  return rawName;
}

/**
 * Inspect Vue template bindings through the pinned Vue compiler AST before a
 * generic canonical validator can replace a credential-specific rejection
 * with a less precise unsupported-identifier error. Attribute values are
 * never included in the diagnostic.
 */
function assertVueTemplateSensitiveBindingsSafe(
  source: string | MiniProgramSource,
  framework: MiniAppSourceFramework,
  label: string,
): void {
  if (typeof source !== "string" || (framework !== "vue2" && framework !== "vue3")) {
    return;
  }

  let root: unknown = null;
  try {
    if (framework === "vue3") {
      const compiler = require("@vue/compiler-sfc") as {
        readonly parse: (
          input: string,
          options: { readonly filename: string },
        ) => {
          readonly errors: readonly unknown[];
          readonly descriptor: {
            readonly template?: { readonly ast?: unknown } | null;
          };
        };
      };
      const parsed = compiler.parse(source, { filename: label });
      if (parsed.errors.length > 0) {
        block(
          "MINIAPP_WORKER_SECRET_SCAN_PARSE_BLOCKED",
          `${label} could not be structurally segmented for template binding scanning`,
          "source-parse",
        );
      }
      root = parsed.descriptor.template?.ast ?? null;
    } else {
      const compiler = require("vue-template-compiler/build") as {
        readonly parseComponent: (input: string) => {
          readonly template?: { readonly content: string } | null;
        };
        readonly compile: (input: string) => {
          readonly ast?: unknown;
          readonly errors?: readonly unknown[];
        };
      };
      const descriptor = compiler.parseComponent(source);
      if (descriptor.template !== null && descriptor.template !== undefined) {
        const compiled = compiler.compile(descriptor.template.content);
        if ((compiled.errors ?? []).length > 0) {
          block(
            "MINIAPP_WORKER_SECRET_SCAN_PARSE_BLOCKED",
            `${label} could not be structurally segmented for template binding scanning`,
            "source-parse",
          );
        }
        root = compiled.ast ?? null;
      }
    }
  } catch (error) {
    if (error instanceof MiniAppWorkerError) throw error;
    block(
      "MINIAPP_WORKER_SECRET_SCAN_PARSE_BLOCKED",
      `${label} could not be structurally segmented for template binding scanning`,
      "source-parse",
    );
  }

  const rejectIfSensitive = (name: unknown): void => {
    if (typeof name === "string" && isSensitiveName(name)) {
      block(
        "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
        `${label} template declares a sensitive attribute; credential propagation is outside this worker and the value is intentionally not reported`,
        "canonical-validation",
      );
    }
  };
  const visit = (node: unknown): void => {
    if (!isPlainObject(node)) return;

    if (Array.isArray(node.props)) {
      for (const candidate of node.props) {
        if (!isPlainObject(candidate)) continue;
        if (candidate.type === 6) {
          rejectIfSensitive(candidate.name);
        } else if (
          candidate.type === 7 &&
          candidate.name === "bind" &&
          isPlainObject(candidate.arg) &&
          candidate.arg.isStatic !== false
        ) {
          rejectIfSensitive(candidate.arg.content);
        }
      }
    }

    if (Array.isArray(node.attrsList)) {
      for (const candidate of node.attrsList) {
        if (!isPlainObject(candidate) || typeof candidate.name !== "string") continue;
        rejectIfSensitive(vue2TemplateBindingName(candidate.name));
      }
    }

    if (Array.isArray(node.children)) node.children.forEach(visit);
  };
  visit(root);
}

function assertSensitiveAstBindingsSafe(
  code: string,
  label: string,
  scriptKind: ts.ScriptKind,
  stage: "request-validation" | "local-emission" = "request-validation",
): void {
  const sourceFile = ts.createSourceFile(
    label,
    code,
    ts.ScriptTarget.ES2022,
    true,
    scriptKind,
  );
  const visit = (node: ts.Node): void => {
    if (
      ts.isComputedPropertyName(node) &&
      staticStringExpression(node.expression) === null
    ) {
      blockUnresolvedComputedBinding(`${label}:computed-property`, stage);
    } else if (ts.isVariableDeclaration(node) && node.initializer !== undefined) {
      for (const name of bindingNames(node.name)) {
        if (isSensitiveName(name)) {
          blockUnsafeSensitiveBinding(name, node.initializer, `${label}:variable`, stage);
        }
      }
    } else if (ts.isParameter(node)) {
      for (const name of bindingNames(node.name)) {
        if (isSensitiveName(name)) {
          blockUnsafeSensitiveBinding(name, node.initializer, `${label}:parameter`, stage);
        }
      }
    } else if (ts.isPropertySignature(node)) {
      const name = propertyNameText(node.name);
      if (name !== null && isSensitiveName(name)) {
        blockUnsafeSensitiveBinding(name, undefined, `${label}:type-property`, stage);
      }
    } else if (ts.isPropertyAssignment(node)) {
      const name = propertyNameText(node.name);
      if (name !== null && isSensitiveName(name)) {
        blockUnsafeSensitiveBinding(name, node.initializer, `${label}:property`, stage);
      }
    } else if (ts.isShorthandPropertyAssignment(node) && isSensitiveName(node.name.text)) {
      blockUnsafeSensitiveBinding(node.name.text, node.name, `${label}:property`, stage);
    } else if (ts.isPropertyDeclaration(node)) {
      const name = propertyNameText(node.name);
      if (name !== null && isSensitiveName(name)) {
        blockUnsafeSensitiveBinding(name, node.initializer, `${label}:class-property`, stage);
      }
    } else if (ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node)) {
      const name = propertyNameText(node.name);
      if (name !== null && isSensitiveName(name)) {
        blockUnsafeSensitiveBinding(name, undefined, `${label}:accessor`, stage);
      }
    } else if (ts.isBinaryExpression(node)) {
      const operator = node.operatorToken.kind;
      if (
        operator >= ts.SyntaxKind.FirstAssignment &&
        operator <= ts.SyntaxKind.LastAssignment
      ) {
        const name = assignedExpressionName(node.left);
        if (name !== null && isSensitiveName(name)) {
          blockUnsafeSensitiveBinding(name, node.right, `${label}:assignment`, stage);
        } else if (name === null) {
          let assigned: ts.Expression = node.left;
          while (ts.isParenthesizedExpression(assigned)) assigned = assigned.expression;
          if (
            ts.isElementAccessExpression(assigned) &&
            (assigned.argumentExpression === undefined ||
              staticStringExpression(assigned.argumentExpression) === null)
          ) {
            blockUnresolvedComputedBinding(`${label}:computed-assignment`, stage);
          }
        }
      }
    } else if (ts.isJsxAttribute(node) && ts.isIdentifier(node.name)) {
      const name = node.name.text;
      if (isSensitiveName(name)) {
        const expression = node.initializer !== undefined && ts.isJsxExpression(node.initializer)
          ? node.initializer.expression
          : node.initializer;
        blockUnsafeSensitiveBinding(name, expression, `${label}:jsx-attribute`, stage);
      }
    } else if (ts.isCallExpression(node)) {
      const callName = assignedExpressionName(node.expression);
      const normalized = callName === null ? "" : normalizedSensitiveName(callName);
      const setterTarget = normalized.startsWith("set") ? normalized.slice(3) : "";
      if (
        callName !== null &&
        (normalized === "setcookie" || isSensitiveName(setterTarget))
      ) {
        blockUnsafeSensitiveBinding(
          callName,
          node.arguments[node.arguments.length - 1],
          `${label}:sensitive-setter`,
          stage,
        );
      }
      if (
        ts.isPropertyAccessExpression(node.expression) &&
        node.expression.name.text === "setItem" &&
        node.arguments[0] !== undefined
      ) {
        const key = staticStringExpression(node.arguments[0]);
        if (key === null) {
          blockUnresolvedComputedBinding(`${label}:setItem`, stage);
        }
        if (isSensitiveName(key)) {
          blockUnsafeSensitiveBinding(
            key,
            node.arguments[1],
            `${label}:setItem`,
            stage,
          );
        }
      }
      if (
        ts.isPropertyAccessExpression(node.expression) &&
        ts.isIdentifier(node.expression.expression) &&
        node.expression.expression.text === "Object" &&
        node.expression.name.text === "defineProperty" &&
        node.arguments[1] !== undefined
      ) {
        const key = staticStringExpression(node.arguments[1]);
        if (key === null) {
          blockUnresolvedComputedBinding(`${label}:defineProperty`, stage);
        }
        const descriptor = node.arguments[2];
        const value = descriptor !== undefined && ts.isObjectLiteralExpression(descriptor)
          ? descriptor.properties.find((property) =>
              ts.isPropertyAssignment(property) && propertyNameText(property.name) === "value",
            )
          : undefined;
        if (isSensitiveName(key)) {
          blockUnsafeSensitiveBinding(
            key,
            value !== undefined && ts.isPropertyAssignment(value) ? value.initializer : undefined,
            `${label}:defineProperty`,
            stage,
          );
        }
      }
      if (
        ts.isPropertyAccessExpression(node.expression) &&
        (node.expression.name.text === "set" || node.expression.name.text === "append") &&
        node.arguments[0] !== undefined
      ) {
        const key = staticStringExpression(node.arguments[0]);
        if (key === null) {
          blockUnresolvedComputedBinding(`${label}:header-setter`, stage);
        }
        if (isSensitiveName(key)) {
          blockUnsafeSensitiveBinding(
            key,
            node.arguments[1],
            `${label}:header-setter`,
            stage,
          );
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
}

function validateFileName(fileName: string): void {
  if (!SAFE_FILE_NAME.test(fileName)) {
    block("MINIAPP_WORKER_UNSAFE_FILE_NAME", "fileName must be a basename of 1-128 ASCII letters, digits, dot, underscore or hyphen");
  }
}

function sourceByteLength(value: string): number {
  return Buffer.byteLength(value, "utf8");
}

function validateSourceString(source: string, label: string): void {
  if (sourceByteLength(source) > MAX_SOURCE_BYTES) {
    block("MINIAPP_WORKER_SOURCE_TOO_LARGE", `${label} exceeds ${MAX_SOURCE_BYTES} UTF-8 bytes`);
  }
  if (source.includes("\u0000")) block("MINIAPP_WORKER_UNSAFE_SOURCE", `${label} contains a NUL byte`);
}

function validateSource(value: unknown, framework: MiniAppSourceFramework): string | MiniProgramSource {
  if (framework === "miniprogram") {
    if (!isPlainObject(value)) {
      block("MINIAPP_WORKER_SCHEMA_VIOLATION", "miniprogram source must be an object with exactly wxml and js strings");
    }
    const object = value as Record<string, unknown>;
    exactKeys(object, ["wxml", "js"], "miniprogram source");
    const wxml = requiredString(object, "wxml");
    const js = requiredString(object, "js");
    validateSourceString(wxml, "source.wxml");
    validateSourceString(js, "source.js");
    return { wxml, js };
  }

  if (typeof value !== "string") {
    block("MINIAPP_WORKER_SCHEMA_VIOLATION", `${framework} source must be a string`);
  }
  validateSourceString(value as string, "source");
  return value as string;
}

function validateSourceFramework(value: unknown): MiniAppSourceFramework {
  if (typeof value !== "string" || !(MINI_APP_SOURCE_FRAMEWORKS as readonly string[]).includes(value)) {
    block(
      "MINIAPP_WORKER_UNSUPPORTED_SOURCE_FRAMEWORK",
      `sourceFramework must be one of ${MINI_APP_SOURCE_FRAMEWORKS.join(", ")}; H5, Flutter and other unlisted inputs are BLOCKED`,
    );
  }
  return value as MiniAppSourceFramework;
}

function validateTargetPlatform(value: unknown): MiniAppPlatform {
  if (typeof value !== "string" || !(MINI_APP_PLATFORMS as readonly string[]).includes(value)) {
    block("MINIAPP_WORKER_UNSUPPORTED_TARGET_PLATFORM", `targetPlatform must be one of ${MINI_APP_PLATFORMS.join(", ")}`);
  }
  return value as MiniAppPlatform;
}

function validateSourceTuple(
  framework: MiniAppSourceFramework,
  sourceFrameworkVersion: string,
  sourceLanguageVersion: string,
): void {
  const profile = MINI_APP_SOURCE_PARSER_PROFILES[framework];
  if (
    sourceFrameworkVersion !== profile.sourceFrameworkVersion ||
    sourceLanguageVersion !== profile.sourceLanguageVersion
  ) {
    block(
      "MINIAPP_WORKER_UNSUPPORTED_SOURCE_TUPLE",
      `${framework} is only bound to source framework/language tuple ${profile.sourceFrameworkVersion}/${profile.sourceLanguageVersion}`,
    );
  }
}

function validateTargetTuple(
  platform: MiniAppPlatform,
  platformVersion: string,
  toolchainVersion: string,
  profileVersion: string,
): void {
  const profile = MINI_APP_TARGET_GENERATOR_PROFILES[platform as keyof typeof MINI_APP_TARGET_GENERATOR_PROFILES] as
    | MiniAppTargetGeneratorProfile
    | undefined;
  if (
    profile === undefined ||
    platformVersion !== profile.platformVersion ||
    toolchainVersion !== profile.toolchainVersion ||
    profileVersion !== profile.profileVersion
  ) {
    block(
      "MINIAPP_WORKER_UNSUPPORTED_TARGET_TUPLE",
      profile === undefined
        ? `${platform} has no declared platform/toolchain/profile tuple in this worker`
        : `${platform} is only bound to target platform/toolchain/profile tuple ${profile.platformVersion}/${profile.toolchainVersion}/${profile.profileVersion}`,
    );
  }
}

function validateComponentRegistry(
  value: unknown,
  framework: MiniAppSourceFramework,
): readonly MiniAppComponentRegistryEntry[] {
  if (!Array.isArray(value)) {
    block("MINIAPP_WORKER_SCHEMA_VIOLATION", "componentRegistry must be an array");
  }
  if (value.length > 256) {
    block("MINIAPP_WORKER_SCHEMA_VIOLATION", "componentRegistry exceeds 256 entries");
  }
  const names = new Set<string>();
  const candidates: readonly unknown[] = value;
  return candidates.map((candidate, index) => {
    if (!isPlainObject(candidate)) {
      block("MINIAPP_WORKER_SCHEMA_VIOLATION", `componentRegistry[${index}] must be a plain object`);
    }
    const object = candidate as Record<string, unknown>;
    exactKeys(
      object,
      ["name", "source", "fileName", "canonicalComponentDigest"],
      `componentRegistry[${index}]`,
    );
    const name = requiredString(object, "name");
    const fileName = requiredString(object, "fileName");
    validateFileName(fileName);
    const source = validateSource(object.source, framework);
    const canonicalComponentDigest = requiredString(object, "canonicalComponentDigest");
    if (!SAFE_COMPONENT_NAME.test(name)) {
      block(
        "MINIAPP_WORKER_SCHEMA_VIOLATION",
        `componentRegistry[${index}].name must be a bounded PascalCase component name`,
      );
    }
    if (names.has(name)) {
      block("MINIAPP_WORKER_SCHEMA_VIOLATION", `componentRegistry contains duplicate component name ${name}`);
    }
    if (!SHA256_DIGEST.test(canonicalComponentDigest)) {
      block(
        "MINIAPP_WORKER_SCHEMA_VIOLATION",
        `componentRegistry[${index}].canonicalComponentDigest must be sha256:<64 lowercase hex>`,
      );
    }
    names.add(name);
    return { name, source, fileName, canonicalComponentDigest };
  });
}

export function parseMiniAppWorkerRequest(value: unknown): MiniAppWorkerRequest {
  if (!isPlainObject(value)) block("MINIAPP_WORKER_SCHEMA_VIOLATION", "request must be a plain JSON object");
  const object = value as Record<string, unknown>;
  const action = object.action;
  if (typeof action !== "string") block("MINIAPP_WORKER_SCHEMA_VIOLATION", "action must be a string");
  if (action !== "analyze" && action !== "emit") {
    block("MINIAPP_WORKER_UNKNOWN_ACTION", `unknown action ${JSON.stringify(action)}; expected analyze or emit`);
  }

  exactKeys(
    object,
    action === "analyze"
      ? [
          "action",
          "sourceFramework",
          "sourceFrameworkVersion",
          "sourceLanguageVersion",
          "source",
          "fileName",
        ]
      : [
          "action",
          "sourceFramework",
          "sourceFrameworkVersion",
          "sourceLanguageVersion",
          "source",
          "fileName",
          "targetPlatform",
          "platformVersion",
          "toolchainVersion",
          "profileVersion",
          "componentRegistry",
        ],
    `${action} request`,
  );
  const framework = validateSourceFramework(object.sourceFramework);
  const sourceFrameworkVersion = requiredString(object, "sourceFrameworkVersion");
  const sourceLanguageVersion = requiredString(object, "sourceLanguageVersion");
  validateSourceTuple(framework, sourceFrameworkVersion, sourceLanguageVersion);
  const fileName = requiredString(object, "fileName");
  validateFileName(fileName);
  const source = validateSource(object.source, framework);

  if (action === "analyze") {
    return {
      action,
      sourceFramework: framework,
      sourceFrameworkVersion,
      sourceLanguageVersion,
      source,
      fileName,
    };
  }
  const targetPlatform = validateTargetPlatform(object.targetPlatform);
  const platformVersion = requiredString(object, "platformVersion");
  const toolchainVersion = requiredString(object, "toolchainVersion");
  const profileVersion = requiredString(object, "profileVersion");
  validateTargetTuple(targetPlatform, platformVersion, toolchainVersion, profileVersion);
  return {
    action,
    sourceFramework: framework,
    sourceFrameworkVersion,
    sourceLanguageVersion,
    source,
    fileName,
    targetPlatform,
    platformVersion,
    toolchainVersion,
    profileVersion,
    componentRegistry: validateComponentRegistry(object.componentRegistry, framework),
  };
}

function parseSource(request: MiniAppWorkerRequest): ComponentDef {
  switch (request.sourceFramework) {
    case "react":
    case "typescript":
      return parseReactComponent(request.source as string, request.fileName);
    case "react-native":
      block(
        "MINIAPP_WORKER_REACT_NATIVE_SEMANTICS_NOT_IMPLEMENTED",
        "React Native View/Text/Pressable and native event semantics are not implemented; the web JSX adapter is not an allowed substitute",
        "source-parse",
      );
    case "vue2":
      return parseVue2Component(request.source as string, request.fileName);
    case "vue3":
      return parseVue3Component(request.source as string, request.fileName);
    case "miniprogram":
      return parseMiniProgramComponent(request.source as MiniProgramSource, request.fileName);
  }
}

/** JSON-compatible canonicalization: object keys sorted, undefined omitted. */
function canonicalJsonValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((entry) => canonicalJsonValue(entry));
  if (isPlainObject(value)) {
    const result: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort()) {
      const child = value[key];
      if (child !== undefined) result[key] = canonicalJsonValue(child);
    }
    return result;
  }
  return value;
}

export function canonicalComponentDigest(component: ComponentDef): string {
  const canonical = JSON.stringify(canonicalJsonValue(component));
  return `sha256:${createHash("sha256").update(canonical, "utf8").digest("hex")}`;
}

function canonicalDigest(value: unknown): string {
  return `sha256:${createHash("sha256")
    .update(JSON.stringify(canonicalJsonValue(value)), "utf8")
    .digest("hex")}`;
}

interface RawSourceIdentity {
  readonly rawSourceSha256: string;
  readonly rawSourceBytes: number;
}

function rawSourceIdentity(source: string | MiniProgramSource): RawSourceIdentity {
  if (typeof source === "string") {
    const bytes = Buffer.from(source, "utf8");
    return {
      rawSourceSha256: `sha256:${createHash("sha256").update(bytes).digest("hex")}`,
      rawSourceBytes: bytes.byteLength,
    };
  }
  const wxml = Buffer.from(source.wxml, "utf8");
  const js = Buffer.from(source.js, "utf8");
  // NUL is rejected in validateSourceString, so labelled framing is
  // unambiguous while rawSourceBytes remains the exact payload byte total.
  const framed = Buffer.concat([
    Buffer.from("wxml\u0000", "utf8"),
    wxml,
    Buffer.from("\u0000js\u0000", "utf8"),
    js,
  ]);
  return {
    rawSourceSha256: `sha256:${createHash("sha256").update(framed).digest("hex")}`,
    rawSourceBytes: wxml.byteLength + js.byteLength,
  };
}

function parserProfileDigest(request: MiniAppWorkerRequest): string {
  const modules: Readonly<Record<MiniAppSourceFramework, readonly string[]>> = {
    react: ["<miniapp-worker>", "./parsers/react", "./models"],
    typescript: ["<miniapp-worker>", "./parsers/react", "./models"],
    "react-native": ["<miniapp-worker>", "./parsers/react", "./models"],
    vue2: ["<miniapp-worker>", "./parsers/vue2", "./parsers/expressions", "./models"],
    vue3: [
      "<miniapp-worker>",
      "./parsers/vue3",
      "./parsers/expressions",
      "./parsers/react",
      "./models",
    ],
    miniprogram: [
      "<miniapp-worker>",
      "./parsers/miniprogram",
      "./parsers/expressions",
      "./models",
    ],
  };
  return canonicalDigest({
    declaration: MINI_APP_SOURCE_PARSER_PROFILES[request.sourceFramework],
    dependency_evidence: engineDependencyEvidence(),
    implementation_modules: implementationModuleIdentities(
      modules[request.sourceFramework],
    ),
    installed_parser_packages: installedParserPackageIdentities(
      request.sourceFramework,
    ),
  });
}

interface ImplementationModuleIdentity {
  readonly logicalModule: string;
  readonly sha256: string;
  readonly bytes: number;
}

interface InstalledPackageSpec {
  readonly packageName: string;
  readonly entryModule: string;
  readonly expectedVersion: string;
}

interface InstalledPackageIdentity {
  readonly package_name: string;
  readonly package_version: string;
  readonly resolved_entry: string;
  readonly entry_sha256: string;
  readonly entry_bytes: number;
  readonly package_json_sha256: string;
  readonly package_json_bytes: number;
}

interface DependencyFileIdentity {
  readonly name: string;
  readonly sha256: string;
  readonly bytes: number;
}

function sha256FileIdentity(name: string, filePath: string): DependencyFileIdentity {
  const content = fs.readFileSync(filePath);
  return {
    name,
    sha256: `sha256:${createHash("sha256").update(content).digest("hex")}`,
    bytes: content.byteLength,
  };
}

function findPackageRoot(
  packageName: string,
  entryPath: string,
): { readonly root: string; readonly packageJsonPath: string; readonly version: string } {
  let current = path.dirname(fs.realpathSync(entryPath));
  for (;;) {
    const packageJsonPath = path.join(current, "package.json");
    if (fs.existsSync(packageJsonPath)) {
      const parsed = JSON.parse(fs.readFileSync(packageJsonPath, "utf8")) as {
        readonly name?: unknown;
        readonly version?: unknown;
      };
      if (parsed.name === packageName && typeof parsed.version === "string") {
        return { root: current, packageJsonPath, version: parsed.version };
      }
    }
    const parent = path.dirname(current);
    if (parent === current) {
      block(
        "MINIAPP_WORKER_PARSER_PACKAGE_EVIDENCE_MISSING",
        `installed parser package metadata is unavailable for ${packageName}`,
      );
    }
    current = parent;
  }
}

function installedPackageIdentity(spec: InstalledPackageSpec): InstalledPackageIdentity {
  const entryPath = fs.realpathSync(require.resolve(spec.entryModule));
  const packageInfo = findPackageRoot(spec.packageName, entryPath);
  if (packageInfo.version !== spec.expectedVersion) {
    block(
      "MINIAPP_WORKER_PARSER_PACKAGE_VERSION_MISMATCH",
      `installed parser package ${spec.packageName} does not match declared version ${spec.expectedVersion}`,
    );
  }
  const relativeEntry = path.relative(packageInfo.root, entryPath).split(path.sep).join("/");
  if (
    relativeEntry === "" ||
    relativeEntry === ".." ||
    relativeEntry.startsWith("../") ||
    path.posix.isAbsolute(relativeEntry)
  ) {
    block(
      "MINIAPP_WORKER_PARSER_PACKAGE_EVIDENCE_MISSING",
      `resolved parser entry escapes installed package ${spec.packageName}`,
    );
  }
  const entry = sha256FileIdentity(relativeEntry, entryPath);
  const packageJson = sha256FileIdentity("package.json", packageInfo.packageJsonPath);
  return {
    package_name: spec.packageName,
    package_version: packageInfo.version,
    resolved_entry: relativeEntry,
    entry_sha256: entry.sha256,
    entry_bytes: entry.bytes,
    package_json_sha256: packageJson.sha256,
    package_json_bytes: packageJson.bytes,
  };
}

function installedParserPackageIdentities(
  framework: MiniAppSourceFramework,
): readonly InstalledPackageIdentity[] {
  const profile = MINI_APP_SOURCE_PARSER_PROFILES[framework];
  const typescript: InstalledPackageSpec = {
    packageName: "typescript",
    entryModule: "typescript",
    expectedVersion: profile.expressionParser === "typescript"
      ? profile.expressionParserVersion as string
      : profile.parserVersion,
  };
  const specs: Readonly<Record<MiniAppSourceFramework, readonly InstalledPackageSpec[]>> = {
    react: [
      typescript,
      {
        packageName: "react",
        entryModule: "react",
        expectedVersion: profile.sourceFrameworkVersion,
      },
    ],
    typescript: [typescript],
    "react-native": [typescript],
    vue2: [
      typescript,
      {
        packageName: "vue-template-compiler",
        entryModule: "vue-template-compiler/build",
        expectedVersion: profile.parserVersion,
      },
    ],
    vue3: [
      typescript,
      {
        packageName: "@vue/compiler-sfc",
        entryModule: "@vue/compiler-sfc",
        expectedVersion: profile.parserVersion,
      },
    ],
    miniprogram: [
      typescript,
      {
        packageName: "@wxml/parser",
        entryModule: "@wxml/parser",
        expectedVersion: profile.parserVersion,
      },
    ],
  };
  return specs[framework].map(installedPackageIdentity);
}

function enginePackageRoot(): string {
  let current = path.resolve(__dirname);
  for (;;) {
    const packageJsonPath = path.join(current, "package.json");
    if (fs.existsSync(packageJsonPath)) {
      const parsed = JSON.parse(fs.readFileSync(packageJsonPath, "utf8")) as {
        readonly name?: unknown;
      };
      if (parsed.name === "@elmos/component-dialect-engine") return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      block(
        "MINIAPP_WORKER_DEPENDENCY_LOCK_EVIDENCE_MISSING",
        "component-dialect-engine package metadata could not be located",
      );
    }
    current = parent;
  }
}

function engineDependencyEvidence(): {
  readonly package_json: DependencyFileIdentity;
  readonly locks: readonly DependencyFileIdentity[];
  readonly evidence_level: "resolved-entry-package-metadata-and-engine-locks";
} {
  const root = enginePackageRoot();
  const locks = ["package-lock.json", "pnpm-lock.yaml"]
    .filter((name) => fs.existsSync(path.join(root, name)))
    .map((name) => sha256FileIdentity(name, path.join(root, name)));
  if (locks.length === 0) {
    block(
      "MINIAPP_WORKER_DEPENDENCY_LOCK_EVIDENCE_MISSING",
      "component-dialect-engine has no package-lock.json or pnpm-lock.yaml evidence",
    );
  }
  return {
    package_json: sha256FileIdentity("package.json", path.join(root, "package.json")),
    locks,
    evidence_level: "resolved-entry-package-metadata-and-engine-locks",
  };
}

function implementationModuleIdentities(
  logicalModules: readonly string[],
): readonly ImplementationModuleIdentity[] {
  return logicalModules.map((logicalModule) => {
    const resolved = logicalModule === "<miniapp-worker>"
      ? __filename
      : require.resolve(logicalModule);
    const content = fs.readFileSync(resolved);
    return {
      logicalModule,
      sha256: `sha256:${createHash("sha256").update(content).digest("hex")}`,
      bytes: content.byteLength,
    };
  });
}

function targetGeneratorProfile(request: EmitRequest): MiniAppTargetGeneratorProfile {
  const profile = MINI_APP_TARGET_GENERATOR_PROFILES[
    request.targetPlatform as keyof typeof MINI_APP_TARGET_GENERATOR_PROFILES
  ] as MiniAppTargetGeneratorProfile | undefined;
  if (profile === undefined) {
    // Request validation already establishes this invariant.  Keep the
    // internal lookup fail closed if callers bypass it through an unsafe cast.
    block(
      "MINIAPP_WORKER_UNSUPPORTED_TARGET_TUPLE",
      `${request.targetPlatform} has no declared generator profile`,
    );
  }
  return profile;
}

function targetGeneratorProfileDigest(request: EmitRequest): string {
  return canonicalDigest({
    declaration: targetGeneratorProfile(request),
    dependency_evidence: engineDependencyEvidence(),
    implementation_modules: implementationModuleIdentities([
      "<miniapp-worker>",
      "./emitters/platform-miniapps",
      "./emitters/react",
      "./models",
    ]),
  });
}

function buildProvenance(
  request: MiniAppWorkerRequest,
  generatedArtifacts: unknown | null,
): MiniAppWorkerProvenance {
  const raw = rawSourceIdentity(request.source);
  const requestDigest = canonicalDigest(request);
  const parserDigest = parserProfileDigest(request);
  const emitterDigest = request.action === "emit"
    ? targetGeneratorProfileDigest(request)
    : null;
  const generatedFilesDigest = generatedArtifacts === null
    ? null
    : canonicalDigest(generatedArtifacts);
  return {
    ...raw,
    requestDigest,
    inputDigest: canonicalDigest({
      request_digest: requestDigest,
      raw_source_sha256: raw.rawSourceSha256,
      raw_source_bytes: raw.rawSourceBytes,
      parser_profile_digest: parserDigest,
      emitter_profile_digest: emitterDigest,
    }),
    parserProfileDigest: parserDigest,
    emitterProfileDigest: emitterDigest,
    generatedFilesDigest,
    dependencyEvidenceLevel: "DIRECT_ENTRIES_METADATA_AND_ENGINE_LOCKS",
  };
}

function evidence(
  localEmission: "PASSED" | "NOT_RUN",
): MiniAppWorkerEvidence {
  return {
    requestValidation: "PASSED",
    sourceParse: "PASSED",
    canonicalValidation: "PASSED",
    localEmission,
    externalPlatformBuild: "NOT_RUN",
    externalPlatformRuntime: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  };
}

function errorEvidence(stage: MiniAppWorkerStage | null): MiniAppWorkerEvidence {
  const passedParse =
    stage === "canonical-validation" || stage === "local-emission";
  const passedCanonical = stage === "local-emission";
  return {
    requestValidation:
      stage === null ? "NOT_RUN" : stage === "request-validation" ? "BLOCKED" : "PASSED",
    sourceParse:
      stage === "source-parse" ? "BLOCKED" : passedParse ? "PASSED" : "NOT_RUN",
    canonicalValidation:
      stage === "canonical-validation"
        ? "BLOCKED"
        : passedCanonical
          ? "PASSED"
          : "NOT_RUN",
    localEmission: stage === "local-emission" ? "BLOCKED" : "NOT_RUN",
    externalPlatformBuild: "NOT_RUN",
    externalPlatformRuntime: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  };
}

function boundaryNotes(): MiniAppWorkerNote[] {
  return [
    {
      code: "MINIAPP_EXTERNAL_PLATFORM_BUILD_NOT_RUN",
      category: "evidence-boundary",
      status: "NOT_RUN",
      message: "No official platform IDE or CLI build was executed by this local JSON worker.",
    },
    {
      code: "MINIAPP_EXTERNAL_PLATFORM_RUNTIME_NOT_RUN",
      category: "evidence-boundary",
      status: "NOT_RUN",
      message: "No emulator, simulator, preview runtime or physical device journey was executed.",
    },
    {
      code: "MINIAPP_NOT_CERTIFIED",
      category: "evidence-boundary",
      status: "NOT_CERTIFIED",
      message: "Local parsing and deterministic emission are engineering evidence only.",
    },
  ];
}

function semanticNotes(request: MiniAppWorkerRequest): MiniAppWorkerNote[] {
  const notes: MiniAppWorkerNote[] = [];
  if (request.sourceFramework === "miniprogram") {
    notes.push({
      code: "MINIAPP_SOURCE_CALLBACK_TYPES_UNRECOVERABLE",
      category: "semantic",
      status: "INFORMATIONAL",
      message: "Native mini-program triggerEvent declarations do not encode callback payload types; recovered callbacks remain untyped in canonical IR.",
    });
  }
  if (request.action === "emit") {
    notes.push({
      code: "MINIAPP_SOURCE_STYLES_NOT_TRANSLATED",
      category: "semantic",
      status: "INFORMATIONAL",
      message: "The canonical ComponentDef contains structural classes but no source stylesheet; only deterministic semantic fallback styles are emitted.",
    });
    if (request.targetPlatform === "alipay") {
      notes.push({
        code: "ALIPAY_CALLBACKS_USE_PROPS",
        category: "semantic",
        status: "INFORMATIONAL",
        message: "Canonical callback props are delivered through guarded this.props callbacks, matching the Alipay custom-component model.",
      });
    }
  }
  return notes;
}

function assertRequestSourcesSecretSafe(request: MiniAppWorkerRequest): void {
  const scan = (source: string | MiniProgramSource, label: string): void => {
    if (typeof source === "string") {
      assertNoSecretMaterial(source, label, "request-validation");
    } else {
      assertNoSecretMaterial(source.wxml, `${label}.wxml`, "request-validation");
      assertNoSecretMaterial(source.js, `${label}.js`, "request-validation");
    }
    for (const unit of executableSourceUnits(
      source,
      request.sourceFramework,
      label,
    )) {
      assertSensitiveAstBindingsSafe(unit.code, unit.label, unit.scriptKind);
    }
    assertVueTemplateSensitiveBindingsSafe(source, request.sourceFramework, label);
  };
  scan(request.source, "source");
  if (request.action === "emit") {
    request.componentRegistry.forEach((entry, index) => {
      scan(entry.source, `componentRegistry[${index}].source`);
    });
  }
}

function stagedDialectFailure(error: unknown, stage: MiniAppWorkerStage): never {
  if (error instanceof MiniAppWorkerError) throw error;
  if (error instanceof DialectError) {
    throw new MiniAppWorkerError(error.code, error.reason, stage);
  }
  throw new MiniAppWorkerError(
    "MINIAPP_WORKER_UNEXPECTED_STAGE_FAILURE",
    `an unexpected ${stage} failure was suppressed without exposing internal details`,
    stage,
  );
}

function parseSourceClosed(request: MiniAppWorkerRequest): ComponentDef {
  try {
    return parseSource(request);
  } catch (error) {
    return stagedDialectFailure(error, "source-parse");
  }
}

function validateCanonicalClosed(component: ComponentDef): void {
  try {
    validateComponent(component);
  } catch (error) {
    stagedDialectFailure(error, "canonical-validation");
  }
}

function visitCanonicalNodes(
  node: CanonicalNode,
  visit: (candidate: CanonicalNode) => void,
): void {
  visit(node);
  switch (node.kind) {
    case "element":
      node.children.forEach((child) => visitCanonicalNodes(child, visit));
      return;
    case "conditional":
      visitCanonicalNodes(node.then, visit);
      if (node.else !== null) visitCanonicalNodes(node.else, visit);
      return;
    case "list":
      visitCanonicalNodes(node.body, visit);
      return;
    case "component":
    case "text":
      return;
  }
}

/**
 * Reject secret-shaped runtime bindings even when no literal material appears
 * in the source.  In particular, parser IR must never turn a credential prop
 * or state field into a target MiniApp property/data binding.
 */
function assertCanonicalSensitiveBindingsSafe(component: ComponentDef): void {
  for (const prop of component.props) {
    if (isSensitiveName(prop.name)) {
      block(
        "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
        `canonical component ${component.name} declares sensitive prop ${prop.name}; credential propagation is outside this worker`,
        "canonical-validation",
      );
    }
  }
  for (const state of component.state) {
    if (isSensitiveName(state.name)) {
      block(
        "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
        `canonical component ${component.name} declares sensitive state ${state.name}; credential propagation is outside this worker`,
        "canonical-validation",
      );
    }
  }
  visitCanonicalNodes(component.root, (node) => {
    if (node.kind !== "component") return;
    for (const prop of node.props) {
      if (isSensitiveName(prop.name)) {
        block(
          "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
          `canonical component reference ${node.name} receives sensitive prop ${prop.name}; credential propagation is outside this worker`,
          "canonical-validation",
        );
      }
    }
  });
}

interface ResolvedChildComponent {
  readonly component: ComponentDef;
  readonly canonicalComponentDigest: string;
}

function resolveSameRunRegistry(
  request: EmitRequest,
  parent: ComponentDef,
): ReadonlyMap<string, ResolvedChildComponent> {
  const resolved = new Map<string, ResolvedChildComponent>();
  for (const entry of request.componentRegistry) {
    if (entry.name === parent.name) {
      block(
        "MINIAPP_WORKER_COMPONENT_REGISTRY_PARENT_COLLISION",
        `component registry entry ${entry.name} collides with the emitted parent`,
        "canonical-validation",
      );
    }
    const childRequest: AnalyzeRequest = {
      action: "analyze",
      sourceFramework: request.sourceFramework,
      sourceFrameworkVersion: request.sourceFrameworkVersion,
      sourceLanguageVersion: request.sourceLanguageVersion,
      source: entry.source,
      fileName: entry.fileName,
    };
    const child = parseSourceClosed(childRequest);
    validateCanonicalClosed(child);
    assertCanonicalSensitiveBindingsSafe(child);
    if (child.name !== entry.name) {
      block(
        "MINIAPP_WORKER_COMPONENT_REGISTRY_NAME_MISMATCH",
        `component registry key ${entry.name} does not match parsed child name ${child.name}`,
        "canonical-validation",
      );
    }
    const digest = canonicalComponentDigest(child);
    if (digest !== entry.canonicalComponentDigest) {
      block(
        "MINIAPP_WORKER_COMPONENT_REGISTRY_DIGEST_MISMATCH",
        `component registry digest does not match parsed child ${entry.name}`,
        "canonical-validation",
      );
    }
    resolved.set(entry.name, { component: child, canonicalComponentDigest: digest });
  }
  return resolved;
}

/**
 * ComponentDef deliberately has no nested callback/list binding semantics.
 * The same-run registry therefore needs to prove every invocation is an
 * exact data-prop contract before target markup is emitted.
 */
function inferCanonicalExpressionType(
  expression: Expr,
  values: ReadonlyMap<string, PrimitiveType>,
  scope: ReadonlyMap<string, ListElementShape>,
): PrimitiveType | null {
  switch (expression.kind) {
    case "ident": {
      const local = scope.get(expression.name);
      if (local !== undefined) {
        return local.kind === "primitive" ? local.primitive : null;
      }
      return values.get(expression.name) ?? null;
    }
    case "member": {
      const local = scope.get(expression.object);
      if (local?.kind !== "object") return null;
      const field = local.fields[expression.field];
      return field?.shape.kind === "primitive" ? field.shape.primitive : null;
    }
    case "path":
      return "string";
    case "literal":
      return expression.literal.type === "null" ? null : expression.literal.type;
    case "unaryNot":
      return "boolean";
    case "stringMethod":
      return inferCanonicalExpressionType(expression.receiver, values, scope) === "string" ? "string" : null;
    case "arrayLength":
      return inferCanonicalExpressionType(expression.operand, values, scope) === null ? "number" : "number";
    case "ternary": {
      const thenType = inferCanonicalExpressionType(expression.then, values, scope);
      const elseType = inferCanonicalExpressionType(expression.else, values, scope);
      return thenType !== null && thenType === elseType ? thenType : null;
    }
    case "binary": {
      if (["<", "<=", ">", ">=", "==", "!="].includes(expression.operator)) {
        return "boolean";
      }
      const left = inferCanonicalExpressionType(expression.left, values, scope);
      const right = inferCanonicalExpressionType(expression.right, values, scope);
      if (expression.operator === "+") {
        return left !== null && left === right && (left === "string" || left === "number")
          ? left
          : null;
      }
      if (["-", "*", "/", "%"].includes(expression.operator)) {
        return left === "number" && right === "number" ? "number" : null;
      }
      if (expression.operator === "&&" || expression.operator === "||") {
        return left !== null && left === right ? left : null;
      }
      if (expression.operator === "??") {
        return left !== null && left === right ? left : null;
      }
      return null;
    }
  }
}

function validateSameRunInvocationContracts(
  parent: ComponentDef,
  registry: ReadonlyMap<string, ResolvedChildComponent>,
): void {
  const validateInvocations = (owner: ComponentDef): void => {
    const values = new Map<string, PrimitiveType>();
    const listProps = new Map<string, ListPropDef>();
    for (const prop of owner.props) {
      if (prop.kind === "data") values.set(prop.name, prop.propType);
      if (prop.kind === "list") listProps.set(prop.name, prop);
    }
    for (const state of owner.state) values.set(state.name, state.stateType);

    const visit = (
      node: CanonicalNode,
      scope: ReadonlyMap<string, ListElementShape>,
    ): void => {
      if (node.kind === "component") {
        const child = registry.get(node.name);
        if (child === undefined) {
          // Graph closure owns the primary diagnostic.  Keep this guard closed
          // if the validation order is ever changed.
          block(
            "MINIAPP_WORKER_COMPONENT_REGISTRY_NOT_CLOSED",
            `same-run component registry is missing referenced child ${node.name} from ${owner.name}`,
            "local-emission",
          );
        }
        const declared = new Map(child.component.props.map((prop) => [prop.name, prop]));
        const supplied = new Set(node.props.map((prop) => prop.name));
        for (const prop of node.props) {
          const contract = declared.get(prop.name);
          if (contract === undefined) {
            block(
              "MINIAPP_WORKER_CHILD_PROP_CONTRACT_MISMATCH",
              `${owner.name} passes undeclared prop ${prop.name} to ${node.name}`,
              "local-emission",
            );
          }
          if (contract.kind !== "data") {
            block(
              contract.kind === "callback"
                ? "MINIAPP_WORKER_CHILD_CALLBACK_BINDING_UNSUPPORTED"
                : "MINIAPP_WORKER_CHILD_LIST_BINDING_UNSUPPORTED",
              `${owner.name} cannot pass ${contract.kind} prop ${prop.name} to ${node.name}; nested callback/list binding semantics are outside this worker`,
              "local-emission",
            );
          }
          const suppliedType = inferCanonicalExpressionType(prop.value, values, scope);
          if (suppliedType === null || suppliedType !== contract.propType) {
            block(
              "MINIAPP_WORKER_CHILD_PROP_TYPE_MISMATCH",
              suppliedType === null
                ? `${owner.name} cannot prove the type of prop ${prop.name} passed to ${node.name}`
                : `${owner.name} passes ${suppliedType} prop ${prop.name} to ${node.name}, which requires ${contract.propType}`,
              "local-emission",
            );
          }
        }
        for (const contract of child.component.props) {
          if (contract.kind !== "data") {
            block(
              contract.kind === "callback"
                ? "MINIAPP_WORKER_CHILD_CALLBACK_BINDING_UNSUPPORTED"
                : "MINIAPP_WORKER_CHILD_LIST_BINDING_UNSUPPORTED",
              `${node.name} declares ${contract.kind} prop ${contract.name}; nested callback/list binding semantics are outside this worker`,
              "local-emission",
            );
          }
          if (contract.required && !supplied.has(contract.name)) {
            block(
              "MINIAPP_WORKER_CHILD_PROP_CONTRACT_MISMATCH",
              `${owner.name} omits required prop ${contract.name} from ${node.name}`,
              "local-emission",
            );
          }
        }
        return;
      }
      if (node.kind === "element") {
        node.children.forEach((child) => visit(child, scope));
        return;
      }
      if (node.kind === "conditional") {
        visit(node.then, scope);
        if (node.else !== null) visit(node.else, scope);
        return;
      }
      if (node.kind === "list") {
        const list = listProps.get(node.source);
        if (list === undefined) {
          block(
            "MINIAPP_WORKER_CHILD_PROP_TYPE_MISMATCH",
            `${owner.name} cannot resolve list source ${node.source} while validating child prop types`,
            "local-emission",
          );
        }
        const nested = new Map(scope);
        nested.set(node.itemName, list.element);
        visit(node.body, nested);
      }
    };

    visit(owner.root, new Map());
  };

  validateInvocations(parent);
  for (const child of registry.values()) validateInvocations(child.component);
}

function validateSameRunGraphClosure(
  parent: ComponentDef,
  registry: ReadonlyMap<string, ResolvedChildComponent>,
): void {
  const visiting = new Set<string>();
  const complete = new Set<string>();
  const reachableChildren = new Set<string>();

  const visit = (name: string, component: ComponentDef): void => {
    if (visiting.has(name)) {
      block(
        "MINIAPP_WORKER_COMPONENT_REGISTRY_CYCLE",
        `component registry contains a render cycle at ${name}`,
        "local-emission",
      );
    }
    if (complete.has(name)) return;
    visiting.add(name);
    for (const childName of referencedComponents(component)) {
      if (childName === parent.name) {
        block(
          "MINIAPP_WORKER_COMPONENT_REGISTRY_CYCLE",
          `component ${name} renders parent ${parent.name}; cross-component cycles are blocked`,
          "local-emission",
        );
      }
      const child = registry.get(childName);
      if (child === undefined) {
        block(
          "MINIAPP_WORKER_COMPONENT_REGISTRY_NOT_CLOSED",
          `same-run component registry is missing referenced child ${childName} from ${name}`,
          "local-emission",
        );
      }
      reachableChildren.add(childName);
      visit(childName, child.component);
    }
    visiting.delete(name);
    complete.add(name);
  };

  visit(parent.name, parent);
  const unrelated = [...registry.keys()]
    .filter((name) => !reachableChildren.has(name))
    .sort();
  if (unrelated.length > 0) {
    block(
      "MINIAPP_WORKER_COMPONENT_REGISTRY_NOT_CLOSED",
      `same-run component registry contains unrelated children: ${unrelated.join(",")}`,
      "local-emission",
    );
  }
}

/**
 * Reusable fail-closed boundary for generated artifact maps.  The exception
 * reports only the file key and rule identifier, never the matched material.
 */
export function assertMiniAppGeneratedFilesSecretSafe(
  files: Readonly<Record<string, string>>,
): void {
  for (const name of Object.keys(files).sort()) {
    const content = files[name];
    if (content === undefined) {
      block(
        "MINIAPP_WORKER_GENERATED_FILE_MISSING",
        `emitter declared generated file ${name} without string content`,
        "local-emission",
      );
    }
    assertNoSecretMaterial(content as string, `generated.${name}`, "local-emission");
    if (
      name === "js" ||
      /\.(?:[cm]?js|[cm]?ts|jsx|tsx)$/iu.test(name)
    ) {
      assertSensitiveAstBindingsSafe(
        content as string,
        `generated.${name}`,
        /(?:tsx|jsx)$/iu.test(name) ? ts.ScriptKind.TSX : ts.ScriptKind.JS,
        "local-emission",
      );
    }
  }
}

function generatedFileIdentities(
  files: Readonly<Record<string, string>>,
): Readonly<Record<string, MiniAppGeneratedFileIdentity>> {
  return Object.fromEntries(
    Object.keys(files).sort().map((name) => {
      const content = files[name];
      if (content === undefined) {
        block(
          "MINIAPP_WORKER_GENERATED_FILE_MISSING",
          `emitter declared generated file ${name} without string content`,
          "local-emission",
        );
      }
      return [name, {
        sha256: `sha256:${createHash("sha256").update(content as string, "utf8").digest("hex")}`,
        bytes: Buffer.byteLength(content as string, "utf8"),
      }];
    }),
  );
}

interface ClosedMiniAppEmission {
  readonly parent: ReturnType<typeof emitPlatformMiniApp>;
  readonly childBundles: Readonly<Record<string, MiniAppEmittedChildBundle>>;
  readonly generatedArtifacts: unknown;
}

function emitClosed(
  request: EmitRequest,
  component: ComponentDef,
): ClosedMiniAppEmission {
  try {
    const registry = resolveSameRunRegistry(request, component);
    validateSameRunGraphClosure(component, registry);
    validateSameRunInvocationContracts(component, registry);
    const parent = emitPlatformMiniApp(component, request.targetPlatform);
    assertMiniAppGeneratedFilesSecretSafe(parent.files);
    const childBundles: Record<string, MiniAppEmittedChildBundle> = {};
    for (const name of [...registry.keys()].sort()) {
      const child = registry.get(name);
      if (child === undefined) {
        block(
          "MINIAPP_WORKER_COMPONENT_REGISTRY_NOT_CLOSED",
          `resolved child ${name} disappeared before emission`,
          "local-emission",
        );
      }
      const emission = emitPlatformMiniApp(child.component, request.targetPlatform);
      assertMiniAppGeneratedFilesSecretSafe(emission.files);
      const fileIdentities = generatedFileIdentities(emission.files);
      childBundles[name] = {
        component: child.component,
        canonicalComponentDigest: child.canonicalComponentDigest,
        files: emission.files,
        fileIdentities,
        bundleDigest: canonicalDigest(emission.files),
        bundleBytes: Object.values(fileIdentities).reduce(
          (total, identity) => total + identity.bytes,
          0,
        ),
      };
    }
    return {
      parent,
      childBundles,
      generatedArtifacts: {
        parent: parent.files,
        children: Object.fromEntries(
          Object.entries(childBundles).map(([name, bundle]) => [name, bundle.files]),
        ),
      },
    };
  } catch (error) {
    return stagedDialectFailure(error, "local-emission");
  }
}

export function handleMiniAppWorkerRequest(value: unknown): MiniAppWorkerResponse {
  const request = parseMiniAppWorkerRequest(value);
  try {
    assertRequestSourcesSecretSafe(request);
    const component = parseSourceClosed(request);
    validateCanonicalClosed(component);
    assertCanonicalSensitiveBindingsSafe(component);
    const digest = canonicalComponentDigest(component);
    const notes = [...semanticNotes(request), ...boundaryNotes()];

    if (request.action === "analyze") {
      return {
        ok: true,
        action: "analyze",
        sourceFramework: request.sourceFramework,
        sourceFrameworkVersion: request.sourceFrameworkVersion,
        sourceLanguageVersion: request.sourceLanguageVersion,
        component,
        canonicalComponentDigest: digest,
        provenance: buildProvenance(request, null),
        notes,
        evidence: evidence("NOT_RUN"),
      };
    }

    const emission = emitClosed(request, component);
    return {
      ok: true,
      action: "emit",
      sourceFramework: request.sourceFramework,
      sourceFrameworkVersion: request.sourceFrameworkVersion,
      sourceLanguageVersion: request.sourceLanguageVersion,
      targetPlatform: request.targetPlatform,
      platformVersion: request.platformVersion,
      toolchainVersion: request.toolchainVersion,
      profileVersion: request.profileVersion,
      component,
      canonicalComponentDigest: digest,
      provenance: buildProvenance(request, emission.generatedArtifacts),
      files: emission.parent.files,
      fileIdentities: generatedFileIdentities(emission.parent.files),
      childBundles: emission.childBundles,
      templateExtension: emission.parent.templateExtension,
      styleExtension: emission.parent.styleExtension,
      notes,
      evidence: evidence("PASSED"),
    };
  } catch (error) {
    if (error instanceof MiniAppWorkerError && error.provenance === null) {
      throw new MiniAppWorkerError(
        error.code,
        error.reason,
        error.stage,
        buildProvenance(request, null),
      );
    }
    throw error;
  }
}

function errorResponse(error: unknown): MiniAppErrorResponse {
  const code = error instanceof MiniAppWorkerError
    ? error.code
    : error instanceof DialectError
      ? error.code
      : "MINIAPP_WORKER_INTERNAL_ERROR";
  const message = error instanceof MiniAppWorkerError || error instanceof DialectError
    ? error.message
    : "The worker failed without exposing internal details.";
  return {
    ok: false,
    error: { code, message },
    provenance: error instanceof MiniAppWorkerError ? error.provenance : null,
    notes: boundaryNotes(),
    evidence: errorEvidence(error instanceof MiniAppWorkerError ? error.stage : null),
  };
}

export interface MiniAppWorkerJsonResult {
  stdout: string;
  exitCode: 0 | 1;
}

/** Pure JSON boundary used by the CLI and protocol tests. */
export function runMiniAppWorkerJson(input: string): MiniAppWorkerJsonResult {
  try {
    if (Buffer.byteLength(input, "utf8") > MAX_STDIN_BYTES) {
      block("MINIAPP_WORKER_INPUT_TOO_LARGE", `stdin exceeds ${MAX_STDIN_BYTES} UTF-8 bytes`);
    }
    if (input.trim().length === 0) block("MINIAPP_WORKER_INVALID_JSON", "stdin must contain one JSON object");
    let parsed: unknown;
    try {
      parsed = JSON.parse(input) as unknown;
    } catch {
      block("MINIAPP_WORKER_INVALID_JSON", "stdin must contain exactly one valid JSON value");
    }
    const response = handleMiniAppWorkerRequest(parsed);
    return { stdout: JSON.stringify(response) + "\n", exitCode: 0 };
  } catch (error) {
    return { stdout: JSON.stringify(errorResponse(error)) + "\n", exitCode: 1 };
  }
}

export function runMiniAppWorkerBytes(input: Uint8Array): MiniAppWorkerJsonResult {
  try {
    if (input.byteLength > MAX_STDIN_BYTES) {
      block("MINIAPP_WORKER_INPUT_TOO_LARGE", `stdin exceeds ${MAX_STDIN_BYTES} bytes`);
    }
    let decoded: string;
    try {
      decoded = new TextDecoder("utf-8", { fatal: true }).decode(input);
    } catch {
      block("MINIAPP_WORKER_INVALID_UTF8", "stdin must be valid UTF-8");
    }
    return runMiniAppWorkerJson(decoded);
  } catch (error) {
    return { stdout: JSON.stringify(errorResponse(error)) + "\n", exitCode: 1 };
  }
}

function readBoundedMiniAppWorkerStdin(): Buffer {
  const chunks: Buffer[] = [];
  const buffer = Buffer.allocUnsafe(64 * 1024);
  let bytes = 0;
  for (;;) {
    const count = fs.readSync(0, buffer, 0, buffer.byteLength, null);
    if (count === 0) return Buffer.concat(chunks, bytes);
    bytes += count;
    if (bytes > MAX_STDIN_BYTES) {
      block("MINIAPP_WORKER_INPUT_TOO_LARGE", `stdin exceeds ${MAX_STDIN_BYTES} bytes`);
    }
    chunks.push(Buffer.from(buffer.subarray(0, count)));
  }
}

export function runMiniAppWorkerCli(): void {
  let result: MiniAppWorkerJsonResult;
  try {
    result = runMiniAppWorkerBytes(readBoundedMiniAppWorkerStdin());
  } catch (error) {
    result = { stdout: JSON.stringify(errorResponse(error)) + "\n", exitCode: 1 };
  }
  process.stdout.write(result.stdout);
  process.exitCode = result.exitCode;
}

if (require.main === module) runMiniAppWorkerCli();
