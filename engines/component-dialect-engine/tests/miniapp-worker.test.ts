import { createHash } from "crypto";
import { readFileSync } from "fs";
import { resolve } from "path";

import { emitMiniProgram } from "../src/emitters/miniprogram";
import * as platformMiniapps from "../src/emitters/platform-miniapps";
import { emitVue3 } from "../src/emitters/vue3";
import {
  assertMiniAppGeneratedFilesSecretSafe,
  canonicalComponentDigest,
  handleMiniAppWorkerRequest,
  MINI_APP_SOURCE_PARSER_PROFILES,
  MINI_APP_TARGET_GENERATOR_PROFILES,
  MiniAppAnalyzeResponse,
  MiniAppComponentRegistryEntry,
  MiniAppEmitResponse,
  MiniAppErrorResponse,
  MiniAppWorkerError,
  runMiniAppWorkerBytes,
  runMiniAppWorkerJson,
} from "../src/miniapp-worker";
import { parseReactComponent } from "../src/parsers/react";
import * as reactParser from "../src/parsers/react";

const SIMPLE_REACT = `
function Counter({ label, onDone }: { label: string; onDone: (value: number) => void }) {
  const [count, setCount] = useState<number>(0);
  return (<div><span>{label}</span><button onClick={() => { setCount(count + 1); onDone(count); }}>add</button></div>);
}
`;

const CHILD_REACT = `
function Parent({ label }: { label: string }) {
  return (<div><StatusChip label={label} /></div>);
}
`;

const CHILD_REACT_MISSING_REQUIRED_PROP = `
function Parent() {
  return (<div><StatusChip /></div>);
}
`;

const CHILD_REACT_WITH_EXTRA_PROP = `
function Parent({ label }: { label: string }) {
  return (<div><StatusChip label={label} tone={label} /></div>);
}
`;

const CHILD_REACT_WITH_TYPE_MISMATCH = `
function Parent({ count }: { count: number }) {
  return (<div><StatusChip label={count} /></div>);
}
`;

const STATUS_CHIP_REACT = `
function StatusChip({ label }: { label: string }) {
  return (<span>{label}</span>);
}
`;

const STATUS_CHIP_WITH_BADGE_REACT = `
function StatusChip({ label }: { label: string }) {
  return (<span><Badge label={label} /></span>);
}
`;

const BADGE_REACT = `
function Badge({ label }: { label: string }) {
  return (<strong>{label}</strong>);
}
`;

const STATUS_CHIP_CYCLE_REACT = `
function StatusChip({ label }: { label: string }) {
  return (<span><Parent label={label} /></span>);
}
`;

const EXTRA_REACT = `
function Extra({ label }: { label: string }) {
  return (<em>{label}</em>);
}
`;

const ACTION_CHIP_REACT = `
function ActionChip({ label, onDone }: { label: string; onDone: () => void }) {
  return (<button onClick={() => { onDone(); }}>{label}</button>);
}
`;

const PARENT_WITH_ACTION_CHIP_REACT = `
function Parent({ label }: { label: string }) {
  return (<div><ActionChip label={label} /></div>);
}
`;

const REAL_REACT_NATIVE = `
import { Pressable, Text, View } from "react-native";
function NativeCard({ title }: { title: string }) {
  return (<View><Text>{title}</Text><Pressable><Text>open</Text></Pressable></View>);
}
`;

const REACT_TUPLE = {
  sourceFramework: "react",
  sourceFrameworkVersion: "18.3.1",
  sourceLanguageVersion: "5.9.2",
} as const;

const WECHAT_TUPLE = {
  targetPlatform: "wechat",
  platformVersion: "3.9.1",
  toolchainVersion: "1.06.2504010",
  profileVersion: "2026-08-20.1",
} as const;

const ALIPAY_TUPLE = {
  targetPlatform: "alipay",
  platformVersion: "2.10.2",
  toolchainVersion: "3.9.4",
  profileVersion: "2026-08-20.1",
} as const;

function validAnalyzeRequest(
  overrides: Readonly<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    action: "analyze",
    ...REACT_TUPLE,
    source: SIMPLE_REACT,
    fileName: "Counter.tsx",
    ...overrides,
  };
}

function validEmitRequest(
  overrides: Readonly<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    ...validAnalyzeRequest(),
    action: "emit",
    ...WECHAT_TUPLE,
    componentRegistry: [],
    ...overrides,
  };
}

function jsonError(request: unknown): {
  result: ReturnType<typeof runMiniAppWorkerJson>;
  response: MiniAppErrorResponse;
} {
  const result = runMiniAppWorkerJson(JSON.stringify(request));
  return { result, response: JSON.parse(result.stdout) as MiniAppErrorResponse };
}

function componentRegistryEntry(
  name: string,
  source: string,
): MiniAppComponentRegistryEntry {
  const fileName = `${name}.tsx`;
  const component = parseReactComponent(source, fileName);
  return {
    name,
    source,
    fileName,
    canonicalComponentDigest: canonicalComponentDigest(component),
  };
}

function statusChipRegistryEntry(
  source = STATUS_CHIP_REACT,
): MiniAppComponentRegistryEntry {
  return componentRegistryEntry("StatusChip", source);
}

describe("controlled mini-app JSON worker", () => {
  it("binds parser profiles to the exact installed dependency versions", () => {
    const packageJson = JSON.parse(
      readFileSync(resolve(__dirname, "../package.json"), "utf8"),
    ) as { version: string; dependencies: Record<string, string> };
    expect(MINI_APP_SOURCE_PARSER_PROFILES.react.parserVersion).toBe(
      packageJson.dependencies.typescript,
    );
    expect(MINI_APP_SOURCE_PARSER_PROFILES.react.sourceFrameworkVersion).toBe(
      packageJson.dependencies.react,
    );
    expect(MINI_APP_SOURCE_PARSER_PROFILES.vue3.parserVersion).toBe(
      packageJson.dependencies["@vue/compiler-sfc"],
    );
    expect(MINI_APP_SOURCE_PARSER_PROFILES.vue2.parserVersion).toBe(
      packageJson.dependencies["vue-template-compiler"],
    );
    expect(MINI_APP_SOURCE_PARSER_PROFILES.miniprogram.parserVersion).toBe(
      packageJson.dependencies["@wxml/parser"],
    );
    expect(MINI_APP_SOURCE_PARSER_PROFILES["react-native"].semanticStatus).toBe(
      "BLOCKED",
    );
    expect(Object.keys(MINI_APP_TARGET_GENERATOR_PROFILES).sort()).toEqual([
      "alipay",
      "wechat",
    ]);
    expect(MINI_APP_TARGET_GENERATOR_PROFILES.wechat.generatorVersion).toBe(
      packageJson.version,
    );

    const xiaohongshu = jsonError({
      ...validEmitRequest(),
      targetPlatform: "xiaohongshu",
      platformVersion: "1.0.0",
      toolchainVersion: "1.0.0",
    });
    expect(xiaohongshu.response.error.code).toBe(
      "MINIAPP_WORKER_UNSUPPORTED_TARGET_TUPLE",
    );
    expect(xiaohongshu.response.evidence.requestValidation).toBe("BLOCKED");
    expect(xiaohongshu.response.provenance).toBeNull();
  });

  it("analyzes React with exact tuple, raw-source provenance and separate canonical identity", () => {
    const first = handleMiniAppWorkerRequest(validAnalyzeRequest()) as MiniAppAnalyzeResponse;
    const second = handleMiniAppWorkerRequest(validAnalyzeRequest()) as MiniAppAnalyzeResponse;
    expect(first.ok).toBe(true);
    expect(first.component.name).toBe("Counter");
    expect(first.sourceFrameworkVersion).toBe("18.3.1");
    expect(first.sourceLanguageVersion).toBe("5.9.2");
    expect(first.canonicalComponentDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(first.canonicalComponentDigest).toBe(canonicalComponentDigest(first.component));
    expect(first.provenance.rawSourceSha256).toBe(
      `sha256:${createHash("sha256").update(SIMPLE_REACT, "utf8").digest("hex")}`,
    );
    expect(first.provenance.rawSourceBytes).toBe(Buffer.byteLength(SIMPLE_REACT, "utf8"));
    expect(first.provenance.requestDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(first.provenance.inputDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(first.provenance.parserProfileDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(first.provenance.emitterProfileDigest).toBeNull();
    expect(first.provenance.generatedFilesDigest).toBeNull();
    expect(first.provenance.dependencyEvidenceLevel).toBe(
      "DIRECT_ENTRIES_METADATA_AND_ENGINE_LOCKS",
    );
    expect(second.provenance).toEqual(first.provenance);
    expect(new Set([
      first.canonicalComponentDigest,
      first.provenance.rawSourceSha256,
      first.provenance.requestDigest,
      first.provenance.inputDigest,
      first.provenance.parserProfileDigest,
    ]).size).toBe(5);
    expect(first.evidence).toEqual({
      requestValidation: "PASSED",
      sourceParse: "PASSED",
      canonicalValidation: "PASSED",
      localEmission: "NOT_RUN",
      externalPlatformBuild: "NOT_RUN",
      externalPlatformRuntime: "NOT_RUN",
      certification: "NOT_CERTIFIED",
    });
  });

  it("keeps canonical identity stable when raw formatting changes while raw/request/input identities change", () => {
    const first = handleMiniAppWorkerRequest(validAnalyzeRequest()) as MiniAppAnalyzeResponse;
    const second = handleMiniAppWorkerRequest(
      validAnalyzeRequest({ source: `\n${SIMPLE_REACT}` }),
    ) as MiniAppAnalyzeResponse;
    expect(second.component).toEqual(first.component);
    expect(second.canonicalComponentDigest).toBe(first.canonicalComponentDigest);
    expect(second.provenance.rawSourceSha256).not.toBe(first.provenance.rawSourceSha256);
    expect(second.provenance.requestDigest).not.toBe(first.provenance.requestDigest);
    expect(second.provenance.inputDigest).not.toBe(first.provenance.inputDigest);
    expect(second.provenance.parserProfileDigest).toBe(first.provenance.parserProfileDigest);
  });

  it("analyzes Vue 3 only through its installed @vue/compiler-sfc tuple", () => {
    const canonical = parseReactComponent(SIMPLE_REACT, "Counter.tsx");
    const response = handleMiniAppWorkerRequest({
      action: "analyze",
      sourceFramework: "vue3",
      sourceFrameworkVersion: "3.5.42",
      sourceLanguageVersion: "5.9.2",
      source: emitVue3(canonical),
      fileName: "Counter.vue",
    }) as MiniAppAnalyzeResponse;
    expect(response.component).toEqual(canonical);
  });

  it("blocks real React Native View/Text semantics instead of routing them through web JSX", () => {
    const { result, response } = jsonError({
      action: "analyze",
      sourceFramework: "react-native",
      sourceFrameworkVersion: "0.76.5",
      sourceLanguageVersion: "5.9.2",
      source: REAL_REACT_NATIVE,
      fileName: "NativeCard.tsx",
    });
    expect(result.exitCode).toBe(1);
    expect(response.error.code).toBe(
      "MINIAPP_WORKER_REACT_NATIVE_SEMANTICS_NOT_IMPLEMENTED",
    );
    expect(response.evidence).toMatchObject({
      requestValidation: "PASSED",
      sourceParse: "BLOCKED",
      canonicalValidation: "NOT_RUN",
      localEmission: "NOT_RUN",
      certification: "NOT_CERTIFIED",
    });
    expect(response.provenance?.rawSourceSha256).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(response.provenance?.parserProfileDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(response.provenance?.emitterProfileDigest).toBeNull();
  });

  it("accepts strict native {wxml,js} source only at the installed parser tuple", () => {
    const canonical = parseReactComponent(SIMPLE_REACT, "Counter.tsx");
    const bundle = emitMiniProgram(canonical);
    const response = handleMiniAppWorkerRequest({
      action: "analyze",
      sourceFramework: "miniprogram",
      sourceFrameworkVersion: "0.4.0",
      sourceLanguageVersion: "5.9.2",
      source: { wxml: bundle.wxml, js: bundle.js },
      fileName: "Counter",
    }) as MiniAppAnalyzeResponse;
    expect(response.component.name).toBe("Counter");
    expect(response.provenance.rawSourceBytes).toBe(
      Buffer.byteLength(bundle.wxml, "utf8") + Buffer.byteLength(bundle.js, "utf8"),
    );
    expect(response.notes.map((note) => note.code)).toContain(
      "MINIAPP_SOURCE_CALLBACK_TYPES_UNRECOVERABLE",
    );
  });

  it("emits only after exact target tuple validation and binds emitter/generated identities", () => {
    const wechat = handleMiniAppWorkerRequest(validEmitRequest()) as MiniAppEmitResponse;
    const response = handleMiniAppWorkerRequest({
      ...validEmitRequest(),
      ...ALIPAY_TUPLE,
    }) as MiniAppEmitResponse;
    expect(response.targetPlatform).toBe("alipay");
    expect(response.platformVersion).toBe("2.10.2");
    expect(response.toolchainVersion).toBe("3.9.4");
    expect(response.profileVersion).toBe("2026-08-20.1");
    expect(Object.keys(response.files).sort()).toEqual(["axml", "js", "json", "acss"].sort());
    expect(response.files.axml).toContain('onTap="handleClickButton0"');
    expect(response.fileIdentities.axml).toEqual({
      sha256: `sha256:${createHash("sha256")
        .update(response.files.axml ?? "", "utf8")
        .digest("hex")}`,
      bytes: Buffer.byteLength(response.files.axml ?? "", "utf8"),
    });
    expect(response.provenance.emitterProfileDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(response.provenance.generatedFilesDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(response.provenance.dependencyEvidenceLevel).toBe(
      "DIRECT_ENTRIES_METADATA_AND_ENGINE_LOCKS",
    );
    expect(response.canonicalComponentDigest).toBe(wechat.canonicalComponentDigest);
    expect(response.provenance.rawSourceSha256).toBe(wechat.provenance.rawSourceSha256);
    expect(response.provenance.parserProfileDigest).toBe(
      wechat.provenance.parserProfileDigest,
    );
    expect(response.provenance.emitterProfileDigest).not.toBe(
      wechat.provenance.emitterProfileDigest,
    );
    expect(response.provenance.requestDigest).not.toBe(wechat.provenance.requestDigest);
    expect(response.provenance.inputDigest).not.toBe(wechat.provenance.inputDigest);
    expect(response.provenance.generatedFilesDigest).not.toBe(
      wechat.provenance.generatedFilesDigest,
    );
    expect(response.evidence.localEmission).toBe("PASSED");
    expect(response.evidence.externalPlatformBuild).toBe("NOT_RUN");
    expect(response.evidence.externalPlatformRuntime).toBe("NOT_RUN");
    expect(response.evidence.certification).toBe("NOT_CERTIFIED");
  });

  it("blocks child-component emission unless the exact same-run registry closes references", () => {
    const unresolved = jsonError(validEmitRequest({
      source: CHILD_REACT,
      fileName: "Parent.tsx",
    }));
    expect(unresolved.result.exitCode).toBe(1);
    expect(unresolved.response.error.code).toBe(
      "MINIAPP_WORKER_COMPONENT_REGISTRY_NOT_CLOSED",
    );
    expect(unresolved.response.evidence).toMatchObject({
      requestValidation: "PASSED",
      sourceParse: "PASSED",
      canonicalValidation: "PASSED",
      localEmission: "BLOCKED",
    });
    expect(unresolved.response.provenance?.requestDigest).toMatch(
      /^sha256:[a-f0-9]{64}$/,
    );
    expect(unresolved.response.provenance?.emitterProfileDigest).toMatch(
      /^sha256:[a-f0-9]{64}$/,
    );
    expect(unresolved.response.provenance?.generatedFilesDigest).toBeNull();

    const closedRequest = validEmitRequest({
      source: CHILD_REACT,
      fileName: "Parent.tsx",
      componentRegistry: [statusChipRegistryEntry()],
    });
    const closed = handleMiniAppWorkerRequest(closedRequest) as MiniAppEmitResponse;
    expect(closed.evidence.localEmission).toBe("PASSED");
    expect(closed.files.wxml).toContain("<status-chip");
    expect(Object.keys(closed.childBundles)).toEqual(["StatusChip"]);
    expect(closed.childBundles.StatusChip?.files.wxml).toContain("{{ label }}");
    expect(closed.childBundles.StatusChip?.canonicalComponentDigest).toBe(
      statusChipRegistryEntry().canonicalComponentDigest,
    );
    const childBundle = closed.childBundles.StatusChip;
    expect(childBundle?.bundleDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(childBundle?.bundleBytes).toBe(
      Object.values(childBundle?.fileIdentities ?? {}).reduce(
        (total, identity) => total + identity.bytes,
        0,
      ),
    );
    expect(childBundle?.fileIdentities.wxml?.sha256).toBe(
      `sha256:${createHash("sha256")
        .update(childBundle?.files.wxml ?? "", "utf8")
        .digest("hex")}`,
    );

    const reformattedChild = `\n${STATUS_CHIP_REACT}`;
    const rebound = handleMiniAppWorkerRequest({
      ...closedRequest,
      componentRegistry: [statusChipRegistryEntry(reformattedChild)],
    }) as MiniAppEmitResponse;
    expect(rebound.canonicalComponentDigest).toBe(closed.canonicalComponentDigest);
    expect(rebound.provenance.generatedFilesDigest).toBe(
      closed.provenance.generatedFilesDigest,
    );
    expect(rebound.provenance.requestDigest).not.toBe(closed.provenance.requestDigest);
    expect(rebound.provenance.inputDigest).not.toBe(closed.provenance.inputDigest);

    const digestMismatch = jsonError({
      ...closedRequest,
      componentRegistry: [{
        ...statusChipRegistryEntry(),
        canonicalComponentDigest: `sha256:${"a".repeat(64)}`,
      }],
    });
    expect(digestMismatch.response.error.code).toBe(
      "MINIAPP_WORKER_COMPONENT_REGISTRY_DIGEST_MISMATCH",
    );
    expect(digestMismatch.response.evidence).toMatchObject({
      requestValidation: "PASSED",
      sourceParse: "PASSED",
      canonicalValidation: "BLOCKED",
      localEmission: "NOT_RUN",
    });

    const missingRequired = jsonError(validEmitRequest({
      source: CHILD_REACT_MISSING_REQUIRED_PROP,
      fileName: "Parent.tsx",
      componentRegistry: [statusChipRegistryEntry()],
    }));
    expect(missingRequired.response.error.code).toBe(
      "MINIAPP_WORKER_CHILD_PROP_CONTRACT_MISMATCH",
    );
    expect(missingRequired.response.error.message).toContain("omits required prop label");
    expect(missingRequired.response.evidence.localEmission).toBe("BLOCKED");

    const extraProp = jsonError(validEmitRequest({
      source: CHILD_REACT_WITH_EXTRA_PROP,
      fileName: "Parent.tsx",
      componentRegistry: [statusChipRegistryEntry()],
    }));
    expect(extraProp.response.error.code).toBe(
      "MINIAPP_WORKER_CHILD_PROP_CONTRACT_MISMATCH",
    );
    expect(extraProp.response.error.message).toContain("passes undeclared prop tone");

    const typeMismatch = jsonError(validEmitRequest({
      source: CHILD_REACT_WITH_TYPE_MISMATCH,
      fileName: "Parent.tsx",
      componentRegistry: [statusChipRegistryEntry()],
    }));
    expect(typeMismatch.response.error.code).toBe(
      "MINIAPP_WORKER_CHILD_PROP_TYPE_MISMATCH",
    );
    expect(typeMismatch.response.error.message).toContain(
      "passes number prop label to StatusChip, which requires string",
    );
    expect(typeMismatch.response.evidence.localEmission).toBe("BLOCKED");

    const callbackChild = jsonError(validEmitRequest({
      source: PARENT_WITH_ACTION_CHIP_REACT,
      fileName: "Parent.tsx",
      componentRegistry: [componentRegistryEntry("ActionChip", ACTION_CHIP_REACT)],
    }));
    expect(callbackChild.response.error.code).toBe(
      "MINIAPP_WORKER_CHILD_CALLBACK_BINDING_UNSUPPORTED",
    );
    expect(callbackChild.response.evidence.localEmission).toBe("BLOCKED");
  });

  it("requires transitive registry closure and rejects cycles or unrelated children", () => {
    const request = validEmitRequest({
      source: CHILD_REACT,
      fileName: "Parent.tsx",
      componentRegistry: [
        statusChipRegistryEntry(STATUS_CHIP_WITH_BADGE_REACT),
        componentRegistryEntry("Badge", BADGE_REACT),
      ],
    });
    const transitive = handleMiniAppWorkerRequest(request) as MiniAppEmitResponse;
    expect(Object.keys(transitive.childBundles)).toEqual(["Badge", "StatusChip"]);
    expect(transitive.childBundles.StatusChip?.files.wxml).toContain("<badge");
    expect(transitive.childBundles.Badge?.bundleBytes).toBeGreaterThan(0);

    const cycle = jsonError(validEmitRequest({
      source: CHILD_REACT,
      fileName: "Parent.tsx",
      componentRegistry: [statusChipRegistryEntry(STATUS_CHIP_CYCLE_REACT)],
    }));
    expect(cycle.response.error.code).toBe("MINIAPP_WORKER_COMPONENT_REGISTRY_CYCLE");
    expect(cycle.response.evidence.localEmission).toBe("BLOCKED");

    const unrelated = jsonError(validEmitRequest({
      source: CHILD_REACT,
      fileName: "Parent.tsx",
      componentRegistry: [
        statusChipRegistryEntry(),
        componentRegistryEntry("Extra", EXTRA_REACT),
      ],
    }));
    expect(unrelated.response.error.code).toBe(
      "MINIAPP_WORKER_COMPONENT_REGISTRY_NOT_CLOSED",
    );
    expect(unrelated.response.error.message).toContain("unrelated children");
    expect(unrelated.response.evidence.localEmission).toBe("BLOCKED");
  });

  it("fails closed on source secret material without echoing the matched value", () => {
    const secret = "not-a-real-secret-but-must-never-leak-123456";
    const source = `function C() { const appSecret = "${secret}"; return (<div>safe</div>); }`;
    const { result, response } = jsonError(validAnalyzeRequest({
      source,
      fileName: "C.tsx",
    }));
    expect(result.exitCode).toBe(1);
    expect(response.error.code).toBe("MINIAPP_WORKER_SOURCE_SECRET_MATERIAL");
    expect(response.error.message).toContain("literal-credential-assignment");
    expect(result.stdout).not.toContain(secret);
    expect(response.evidence).toMatchObject({
      requestValidation: "BLOCKED",
      sourceParse: "NOT_RUN",
      canonicalValidation: "NOT_RUN",
      localEmission: "NOT_RUN",
    });
    expect(response.provenance?.rawSourceSha256).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(response.provenance?.requestDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
  });

  it("blocks JWT/Bearer literal text on the source-to-emit path", () => {
    const token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature123";
    const source = `function C() { return (<div>Bearer ${token}</div>); }`;
    const { result, response } = jsonError(validEmitRequest({
      source,
      fileName: "C.tsx",
    }));
    expect(result.exitCode).toBe(1);
    expect(response.error.code).toBe("MINIAPP_WORKER_SOURCE_SECRET_MATERIAL");
    expect(response.error.message).toMatch(/jwt|authorization-token/u);
    expect(result.stdout).not.toContain(token);
    expect(response.evidence).toMatchObject({
      requestValidation: "BLOCKED",
      sourceParse: "NOT_RUN",
      canonicalValidation: "NOT_RUN",
      localEmission: "NOT_RUN",
    });
    expect(response.provenance?.emitterProfileDigest).toMatch(
      /^sha256:[a-f0-9]{64}$/,
    );
    expect(response.provenance?.generatedFilesDigest).toBeNull();
  });

  it.each([
    ["auth token", "authToken", "auth-material-123456789"],
    ["session token", "sessionToken", "session-material-123456789"],
    ["refresh token", "refreshToken", "refresh-material-123456789"],
    ["access token", "accessToken", "access-material-123456789"],
  ])("blocks literal %s assignments before parsing", (_label, key, secret) => {
    const source = `function C() { const ${key} = "${secret}"; return (<div>safe</div>); }`;
    const { result, response } = jsonError(validEmitRequest({
      source,
      fileName: "C.tsx",
    }));
    expect(result.exitCode).toBe(1);
    expect(response.error.code).toBe("MINIAPP_WORKER_SOURCE_SECRET_MATERIAL");
    expect(response.error.message).toContain("literal-credential-assignment");
    expect(result.stdout).not.toContain(secret);
    expect(response.evidence.requestValidation).toBe("BLOCKED");
    expect(response.provenance?.requestDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
  });

  it.each([
    ["array", 'const appSecret = ["raw-secret-123456789"];'],
    ["suffix key", 'const openaiApiKey = ["raw-secret-123456789"];'],
    ["prefixed session key", 'const userSessionToken = ["raw-secret-123456789"];'],
    ["concatenation", 'const appSecret = "vault://tenant/key" + suffix;'],
    ["property", 'const config = { accessToken: resolveToken() };'],
    ["class property", 'class Holder { appSecret = ["raw-secret-123456789"]; }'],
    ["class accessor", 'class Holder { get appSecret() { return "raw-secret-123456789"; } }'],
    ["assignment", 'let sessionToken; sessionToken = getToken();'],
    ["function parameter", 'function helper({ accessToken }) { return accessToken; }'],
    ["header setter", 'const headers = new Headers(); headers.set("authorization", getToken());'],
  ])("blocks AST-level sensitive %s expressions discarded by the component parser", (_label, declaration) => {
    const source = `function C() { const suffix = "x"; ${declaration} return (<div>safe</div>); }`;
    const { result, response } = jsonError(validEmitRequest({
      source,
      fileName: "C.tsx",
    }));
    expect(result.exitCode).toBe(1);
    expect(response.error.code).toBe("MINIAPP_WORKER_SOURCE_SECRET_MATERIAL");
    expect(response.error.message).toMatch(/sensitive binding|only one literal/u);
    expect(result.stdout).not.toContain("raw-secret-123456789");
    expect(response.evidence.requestValidation).toBe("BLOCKED");
    expect(response.provenance?.requestDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
  });

  it("blocks a bare sensitive JSX attribute with no initializer", () => {
    const source = `function C() { return (<Box appSecret />); }`;
    const { response } = jsonError(validEmitRequest({ source, fileName: "C.tsx" }));
    expect(response.error.code).toBe("MINIAPP_WORKER_SOURCE_SECRET_MATERIAL");
    expect(response.error.message).toContain("jsx-attribute");
    expect(response.evidence.requestValidation).toBe("BLOCKED");
  });

  it("allows only an exact vault/kms reference for a sensitive binding", () => {
    const source = `const appSecret = "vault://tenant/app-secret"; function C() { return (<div>safe</div>); }`;
    const response = handleMiniAppWorkerRequest(validAnalyzeRequest({
      source,
      fileName: "C.tsx",
    })) as MiniAppAnalyzeResponse;
    expect(response.ok).toBe(true);
    expect(response.evidence.requestValidation).toBe("PASSED");
    expect(response.provenance.requestDigest).toMatch(/^sha256:[a-f0-9]{64}$/);

    const sensitiveProp = jsonError(validAnalyzeRequest({
      source: `function C({ accessToken }: { accessToken: string }) { return (<div>safe</div>); }`,
      fileName: "C.tsx",
    }));
    expect(sensitiveProp.response.error.code).toBe(
      "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
    );
    expect(sensitiveProp.response.error.message).toMatch(/parameter|type-property/u);
    expect(sensitiveProp.response.evidence.requestValidation).toBe("BLOCKED");
  });

  it("applies AST secret scanning to Vue scripts, native JS and same-request children", () => {
    const vue = jsonError({
      action: "analyze",
      sourceFramework: "vue3",
      sourceFrameworkVersion: "3.5.42",
      sourceLanguageVersion: "5.9.2",
      source: `<script setup lang="ts">const appSecret = ["vue-secret-123456789"];</script><template><div>safe</div></template>`,
      fileName: "C.vue",
    });
    expect(vue.response.error.code).toBe("MINIAPP_WORKER_SOURCE_SECRET_MATERIAL");
    expect(vue.response.evidence.requestValidation).toBe("BLOCKED");
    expect(vue.result.stdout).not.toContain("vue-secret-123456789");

    const vueTemplateProp = jsonError({
      action: "analyze",
      sourceFramework: "vue3",
      sourceFrameworkVersion: "3.5.42",
      sourceLanguageVersion: "5.9.2",
      source: `<script setup lang="ts">import { ref } from "vue"; const ready = ref(false);</script><template><StatusChip access-token="short" /></template>`,
      fileName: "C.vue",
    });
    expect(vueTemplateProp.response.error.code).toBe(
      "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
    );
    expect(vueTemplateProp.response.evidence).toMatchObject({
      requestValidation: "PASSED",
      sourceParse: "PASSED",
      canonicalValidation: "BLOCKED",
    });

    const native = jsonError({
      action: "analyze",
      sourceFramework: "miniprogram",
      sourceFrameworkVersion: "0.4.0",
      sourceLanguageVersion: "5.9.2",
      source: {
        wxml: "<view>safe</view>",
        js: `const sessionToken = ["native-secret-123456789"]; Component({});`,
      },
      fileName: "C",
    });
    expect(native.response.error.code).toBe("MINIAPP_WORKER_SOURCE_SECRET_MATERIAL");
    expect(native.response.evidence.requestValidation).toBe("BLOCKED");
    expect(native.result.stdout).not.toContain("native-secret-123456789");

    const childSource = `const accessToken = ["child-secret-123456789"]; ${STATUS_CHIP_REACT}`;
    const child = jsonError(validEmitRequest({
      source: CHILD_REACT,
      fileName: "Parent.tsx",
      componentRegistry: [componentRegistryEntry("StatusChip", childSource)],
    }));
    expect(child.response.error.code).toBe("MINIAPP_WORKER_SOURCE_SECRET_MATERIAL");
    expect(child.response.evidence.requestValidation).toBe("BLOCKED");
    expect(child.result.stdout).not.toContain("child-secret-123456789");

    for (const [label, declaration, secret] of [
      [
        "constant computed property",
        'const config = { ["access" + "Token"]: ["computed-secret-123456789"] };',
        "computed-secret-123456789",
      ],
      [
        "constant computed assignment",
        'const config: Record<string, unknown> = {}; config["session" + "Token"] = ["assignment-secret-123456789"];',
        "assignment-secret-123456789",
      ],
      [
        "unresolved computed property",
        'const bindingName = resolveName(); const config = { [bindingName]: ["dynamic-secret-123456789"] };',
        "dynamic-secret-123456789",
      ],
    ] as const) {
      const computed = jsonError(validEmitRequest({
        source: `${declaration} function C() { return (<div>safe</div>); }`,
        fileName: "C.tsx",
      }));
      expect(computed.response.error.code).toBe(
        "MINIAPP_WORKER_SOURCE_SECRET_MATERIAL",
      );
      expect(computed.response.error.message).toMatch(
        /sensitive binding|computed binding name/u,
      );
      expect(computed.response.evidence.requestValidation).toBe("BLOCKED");
      expect(computed.result.stdout).not.toContain(secret);
      expect(label).toMatch(/computed/u);
    }
  });

  it("blocks cookie and non-Bearer authorization header material", () => {
    for (const [label, material] of [
      ["cookie", "Cookie: session=header-material-123456789"],
      ["authorization", "Authorization: Token header-material-123456789"],
    ] as const) {
      const source = `function C() { return (<div>${material}</div>); }`;
      const { result, response } = jsonError(validEmitRequest({
        source,
        fileName: "C.tsx",
      }));
      expect(result.exitCode).toBe(1);
      expect(response.error.code).toBe("MINIAPP_WORKER_SOURCE_SECRET_MATERIAL");
      expect(response.error.message).toContain("sensitive-http-header");
      expect(result.stdout).not.toContain(material);
      expect(response.evidence.requestValidation).toBe("BLOCKED");
      expect(response.provenance?.rawSourceSha256).toMatch(/^sha256:[a-f0-9]{64}$/);
      expect(label).toMatch(/cookie|authorization/);
    }
  });

  it("fails closed on generated-file secret material without echoing the matched value", () => {
    const secret = "not-a-real-generated-secret-123456789";
    let caught: unknown;
    try {
      assertMiniAppGeneratedFilesSecretSafe({
        js: `const authorization = "Bearer ${secret}";`,
      });
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(MiniAppWorkerError);
    if (!(caught instanceof MiniAppWorkerError)) {
      throw new Error("expected MiniAppWorkerError");
    }
    expect(caught.code).toBe("MINIAPP_WORKER_GENERATED_SECRET_MATERIAL");
    expect(caught.stage).toBe("local-emission");
    expect(caught.message).toMatch(/authorization-token|literal-credential-assignment/u);
    expect(caught.message).not.toContain(secret);

    let generatedAstCaught: unknown;
    try {
      assertMiniAppGeneratedFilesSecretSafe({
        js: 'const openaiApiKey = ["generated-array-secret-123456789"];',
      });
    } catch (error) {
      generatedAstCaught = error;
    }
    expect(generatedAstCaught).toBeInstanceOf(MiniAppWorkerError);
    if (!(generatedAstCaught instanceof MiniAppWorkerError)) {
      throw new Error("expected generated AST MiniAppWorkerError");
    }
    expect(generatedAstCaught.code).toBe("MINIAPP_WORKER_GENERATED_SECRET_MATERIAL");
    expect(generatedAstCaught.stage).toBe("local-emission");
    expect(generatedAstCaught.message).not.toContain("generated-array-secret-123456789");

    let generatedComputedCaught: unknown;
    try {
      assertMiniAppGeneratedFilesSecretSafe({
        js: 'const config = { ["access" + "Token"]: ["generated-computed-secret-123456789"] };',
      });
    } catch (error) {
      generatedComputedCaught = error;
    }
    expect(generatedComputedCaught).toBeInstanceOf(MiniAppWorkerError);
    if (!(generatedComputedCaught instanceof MiniAppWorkerError)) {
      throw new Error("expected computed generated MiniAppWorkerError");
    }
    expect(generatedComputedCaught.code).toBe(
      "MINIAPP_WORKER_GENERATED_SECRET_MATERIAL",
    );
    expect(generatedComputedCaught.stage).toBe("local-emission");
    expect(generatedComputedCaught.message).not.toContain(
      "generated-computed-secret-123456789",
    );
  });

  it.each([
    ["unknown action", { action: "destroy" }, "MINIAPP_WORKER_UNKNOWN_ACTION"],
    [
      "missing exact source tuple",
      { action: "analyze", sourceFramework: "react", source: SIMPLE_REACT, fileName: "Counter.tsx" },
      "MINIAPP_WORKER_SCHEMA_VIOLATION",
    ],
    [
      "extra request field",
      { ...validAnalyzeRequest(), surprise: true },
      "MINIAPP_WORKER_SCHEMA_VIOLATION",
    ],
    [
      "unsupported H5 source",
      { ...validAnalyzeRequest(), sourceFramework: "h5" },
      "MINIAPP_WORKER_UNSUPPORTED_SOURCE_FRAMEWORK",
    ],
    [
      "unknown source version tuple",
      { ...validAnalyzeRequest(), sourceFrameworkVersion: "18.3.2" },
      "MINIAPP_WORKER_UNSUPPORTED_SOURCE_TUPLE",
    ],
    [
      "unknown target",
      { ...validEmitRequest(), targetPlatform: "baidu" },
      "MINIAPP_WORKER_UNSUPPORTED_TARGET_PLATFORM",
    ],
    [
      "unknown WeChat generator tuple",
      { ...validEmitRequest(), toolchainVersion: "1.06.9999999" },
      "MINIAPP_WORKER_UNSUPPORTED_TARGET_TUPLE",
    ],
    [
      "Douyin without a declared generator tuple",
      {
        ...validEmitRequest(),
        targetPlatform: "douyin",
        platformVersion: "1.0.0",
        toolchainVersion: "1.0.0",
      },
      "MINIAPP_WORKER_UNSUPPORTED_TARGET_TUPLE",
    ],
    [
      "unsafe filename",
      { ...validAnalyzeRequest(), fileName: "../../secret.tsx" },
      "MINIAPP_WORKER_UNSAFE_FILE_NAME",
    ],
    [
      "extra native source field",
      {
        action: "analyze",
        sourceFramework: "miniprogram",
        sourceFrameworkVersion: "0.4.0",
        sourceLanguageVersion: "5.9.2",
        source: { wxml: "<view />", js: "Component({});", json: "{}" },
        fileName: "C",
      },
      "MINIAPP_WORKER_SCHEMA_VIOLATION",
    ],
  ])("fails closed for %s", (_name, request, code) => {
    const { result, response } = jsonError(request);
    expect(result.exitCode).toBe(1);
    expect(response.ok).toBe(false);
    expect(response.error.code).toBe(code);
    expect(response.evidence.requestValidation).toBe("BLOCKED");
    expect(response.evidence.sourceParse).toBe("NOT_RUN");
    expect(response.evidence.localEmission).toBe("NOT_RUN");
    expect(response.evidence.certification).toBe("NOT_CERTIFIED");
    expect(response.provenance).toBeNull();
  });

  it("returns one JSON error object for invalid stdin without leaking a stack", () => {
    const result = runMiniAppWorkerJson("not-json");
    expect(result.exitCode).toBe(1);
    expect(result.stdout.trim().split("\n")).toHaveLength(1);
    const response = JSON.parse(result.stdout) as MiniAppErrorResponse;
    expect(response.error.code).toBe("MINIAPP_WORKER_INVALID_JSON");
    expect(response.error).not.toHaveProperty("stack");
    expect(response.evidence.requestValidation).toBe("BLOCKED");
    expect(response.provenance).toBeNull();

    const invalidUtf8 = runMiniAppWorkerBytes(Buffer.from([0xff]));
    expect(invalidUtf8.exitCode).toBe(1);
    expect(JSON.parse(invalidUtf8.stdout).error.code).toBe("MINIAPP_WORKER_INVALID_UTF8");
    const oversized = runMiniAppWorkerBytes(Buffer.alloc(2 * 1024 * 1024 + 1, 0x20));
    expect(oversized.exitCode).toBe(1);
    expect(JSON.parse(oversized.stdout).error.code).toBe("MINIAPP_WORKER_INPUT_TOO_LARGE");
  });

  it("propagates parser reason codes with source-parse BLOCKED evidence", () => {
    const request = validAnalyzeRequest({
      source: `function C() { useEffect(() => {}, []); return (<div>unsafe</div>); }`,
      fileName: "C.tsx",
    });
    const { response } = jsonError(request);
    expect(response.error.code).toBe("CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT");
    expect(response.evidence).toMatchObject({
      requestValidation: "PASSED",
      sourceParse: "BLOCKED",
      canonicalValidation: "NOT_RUN",
      localEmission: "NOT_RUN",
    });
    expect(response.provenance?.requestDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(response.provenance?.generatedFilesDigest).toBeNull();
  });

  it("classifies unexpected parser errors at the attempted source-parse stage without leaking details", () => {
    const internalDetail = "parser-internal-sensitive-detail";
    const spy = jest
      .spyOn(reactParser, "parseReactComponent")
      .mockImplementationOnce(() => {
        throw new Error(internalDetail);
      });
    const { result, response } = jsonError(validAnalyzeRequest());
    spy.mockRestore();
    expect(response.error.code).toBe("MINIAPP_WORKER_UNEXPECTED_STAGE_FAILURE");
    expect(result.stdout).not.toContain(internalDetail);
    expect(response.evidence).toMatchObject({
      requestValidation: "PASSED",
      sourceParse: "BLOCKED",
      canonicalValidation: "NOT_RUN",
      localEmission: "NOT_RUN",
    });
    expect(response.provenance?.requestDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
  });

  it("classifies unexpected emitter errors at local-emission after parse and canonical validation", () => {
    const internalDetail = "emitter-internal-sensitive-detail";
    const spy = jest
      .spyOn(platformMiniapps, "emitPlatformMiniApp")
      .mockImplementationOnce(() => {
        throw new Error(internalDetail);
      });
    const { result, response } = jsonError(validEmitRequest());
    spy.mockRestore();
    expect(response.error.code).toBe("MINIAPP_WORKER_UNEXPECTED_STAGE_FAILURE");
    expect(result.stdout).not.toContain(internalDetail);
    expect(response.evidence).toMatchObject({
      requestValidation: "PASSED",
      sourceParse: "PASSED",
      canonicalValidation: "PASSED",
      localEmission: "BLOCKED",
    });
    expect(response.provenance?.emitterProfileDigest).toMatch(
      /^sha256:[a-f0-9]{64}$/,
    );
    expect(response.provenance?.generatedFilesDigest).toBeNull();
  });

  it("serializes successful stdin/stdout output as exactly one JSON line", () => {
    const result = runMiniAppWorkerJson(JSON.stringify(validAnalyzeRequest()));
    expect(result.exitCode).toBe(0);
    expect(result.stdout.trim().split("\n")).toHaveLength(1);
    const response = JSON.parse(result.stdout) as MiniAppAnalyzeResponse;
    expect(response.ok).toBe(true);
    expect(response.canonicalComponentDigest).toMatch(/^sha256:[a-f0-9]{64}$/);
    expect(response.provenance.rawSourceSha256).toMatch(/^sha256:[a-f0-9]{64}$/);
  });
});
