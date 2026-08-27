/**
 * Exact target adapter registry.
 *
 * Emitters remain framework-specific, but all of them are reached through
 * this registry.  The registry is the place where a target declares how it
 * handles each semantic domain and what evidence is still required.  It
 * prevents a new emitter from being treated as a complete cross-platform
 * implementation merely because it can print source text.
 */
import type { CrossPlatformComponentIR, SemanticCategory } from "./cross-platform-ir";
import { Framework, ComponentDef } from "./models";
import { emitAngular } from "./emitters/angular";
import { emitArkUI } from "./emitters/arkui";
import { emitFlutter } from "./emitters/flutter";
import { emitMiniProgram } from "./emitters/miniprogram";
import { emitReact } from "./emitters/react";
import { emitReactNative } from "./emitters/react-native";
import { emitSvelte } from "./emitters/svelte";
import { emitVue2 } from "./emitters/vue2";
import { emitVue3 } from "./emitters/vue3";

export interface TargetEmission {
  emitted: string | null;
  emittedFiles: Record<string, string> | null;
  notes: string[];
}

export interface TargetAdapterDescriptor {
  id: string;
  targetFramework: Framework;
  categoryModes: Record<SemanticCategory, "NATIVE" | "ADAPTER" | "HAND_PORTED" | "BLOCKED">;
  requiredRuntime: "BROWSER" | "ANDROID" | "IOS" | "HARMONYOS" | "FLUTTER" | "WECHAT_DEVTOOLS" | "ANGULAR_RUNTIME";
  syntaxEvidence: "AVAILABLE_HERE" | "EXTERNAL_TOOLCHAIN_REQUIRED";
  runtimeEvidence: "AVAILABLE_HERE" | "EXTERNAL_RUNTIME_REQUIRED";
  emit(ir: CrossPlatformComponentIR): TargetEmission;
}

const commonWebModes: Record<SemanticCategory, "NATIVE" | "ADAPTER" | "HAND_PORTED" | "BLOCKED"> = {
  "render-tree": "NATIVE",
  "state-lifecycle": "NATIVE",
  "effects-and-resources": "ADAPTER",
  "data-contracts": "NATIVE",
  "derived-collections": "NATIVE",
  "slots-and-composition": "ADAPTER",
  "platform-semantics": "ADAPTER",
  styling: "ADAPTER",
  "accessibility-and-i18n": "ADAPTER",
};

const nativeClientModes: Record<SemanticCategory, "NATIVE" | "ADAPTER" | "HAND_PORTED" | "BLOCKED"> = {
  "render-tree": "ADAPTER",
  "state-lifecycle": "ADAPTER",
  "effects-and-resources": "ADAPTER",
  "data-contracts": "NATIVE",
  "derived-collections": "ADAPTER",
  "slots-and-composition": "ADAPTER",
  "platform-semantics": "ADAPTER",
  styling: "ADAPTER",
  "accessibility-and-i18n": "ADAPTER",
};

const componentFor = (ir: CrossPlatformComponentIR): ComponentDef => ir.canonical;

export const TARGET_ADAPTERS: { [K in Framework]: TargetAdapterDescriptor } = {
  react: { id: "react-dom-19-component-adapter", targetFramework: "react", categoryModes: commonWebModes, requiredRuntime: "BROWSER", syntaxEvidence: "AVAILABLE_HERE", runtimeEvidence: "AVAILABLE_HERE", emit: (ir) => ({ emitted: emitReact(componentFor(ir)), emittedFiles: null, notes: [] }) },
  typescript: { id: "typescript-react-dom-component-adapter", targetFramework: "typescript", categoryModes: commonWebModes, requiredRuntime: "BROWSER", syntaxEvidence: "AVAILABLE_HERE", runtimeEvidence: "AVAILABLE_HERE", emit: (ir) => ({ emitted: emitReact(componentFor(ir)), emittedFiles: null, notes: [] }) },
  vue3: { id: "vue3-sfc-component-adapter", targetFramework: "vue3", categoryModes: commonWebModes, requiredRuntime: "BROWSER", syntaxEvidence: "AVAILABLE_HERE", runtimeEvidence: "AVAILABLE_HERE", emit: (ir) => ({ emitted: emitVue3(componentFor(ir)), emittedFiles: null, notes: [] }) },
  vue2: { id: "vue2-options-component-adapter", targetFramework: "vue2", categoryModes: commonWebModes, requiredRuntime: "BROWSER", syntaxEvidence: "AVAILABLE_HERE", runtimeEvidence: "AVAILABLE_HERE", emit: (ir) => ({ emitted: emitVue2(componentFor(ir)), emittedFiles: null, notes: componentFor(ir).props.some((p) => p.kind === "callback" && p.paramType !== undefined) ? ["Vue 2 has no typed emit declaration; callback payload types are not representable"] : [] }) },
  angular: { id: "angular-standalone-component-adapter", targetFramework: "angular", categoryModes: commonWebModes, requiredRuntime: "ANGULAR_RUNTIME", syntaxEvidence: "AVAILABLE_HERE", runtimeEvidence: "EXTERNAL_RUNTIME_REQUIRED", emit: (ir) => ({ emitted: emitAngular(componentFor(ir)), emittedFiles: null, notes: [] }) },
  svelte: { id: "svelte-component-adapter", targetFramework: "svelte", categoryModes: commonWebModes, requiredRuntime: "BROWSER", syntaxEvidence: "AVAILABLE_HERE", runtimeEvidence: "AVAILABLE_HERE", emit: (ir) => ({ emitted: emitSvelte(componentFor(ir)), emittedFiles: null, notes: [] }) },
  "react-native": { id: "react-native-pressable-component-adapter", targetFramework: "react-native", categoryModes: nativeClientModes, requiredRuntime: "ANDROID", syntaxEvidence: "AVAILABLE_HERE", runtimeEvidence: "EXTERNAL_RUNTIME_REQUIRED", emit: (ir) => { const result = emitReactNative(componentFor(ir)); return { emitted: result.source, emittedFiles: null, notes: result.notes }; } },
  miniprogram: { id: "wechat-miniapp-component-adapter", targetFramework: "miniprogram", categoryModes: nativeClientModes, requiredRuntime: "WECHAT_DEVTOOLS", syntaxEvidence: "AVAILABLE_HERE", runtimeEvidence: "EXTERNAL_RUNTIME_REQUIRED", emit: (ir) => ({ emitted: null, emittedFiles: emitMiniProgram(componentFor(ir)), notes: ["WeChat mini program styling is emitted as generated WXSS classes; the source project's own CSS was NOT translated", ...(componentFor(ir).props.some((p) => p.kind === "data" && p.required) ? ["WeChat properties cannot express a required prop; required props are emitted with a synthesized default value and will read back as optional"] : []), ...(componentFor(ir).props.some((p) => p.kind === "callback" && p.paramType !== undefined) ? ["WeChat triggerEvent carries an untyped detail object; callback payload types are not representable and will not survive a translation back out of the mini program"] : [])] }) },
  arkui: { id: "harmonyos-arkui-component-adapter", targetFramework: "arkui", categoryModes: nativeClientModes, requiredRuntime: "HARMONYOS", syntaxEvidence: "EXTERNAL_TOOLCHAIN_REQUIRED", runtimeEvidence: "EXTERNAL_RUNTIME_REQUIRED", emit: (ir) => ({ emitted: emitArkUI(componentFor(ir)), emittedFiles: null, notes: ["no ArkTS compiler is installed here, so this output has NOT been verified by a real HarmonyOS toolchain"] }) },
  flutter: { id: "flutter-dart-widget-adapter", targetFramework: "flutter", categoryModes: nativeClientModes, requiredRuntime: "FLUTTER", syntaxEvidence: "EXTERNAL_TOOLCHAIN_REQUIRED", runtimeEvidence: "EXTERNAL_RUNTIME_REQUIRED", emit: (ir) => ({ emitted: emitFlutter(componentFor(ir)), emittedFiles: null, notes: ["the Flutter/Dart toolchain is external to this engine; target analysis and device runtime evidence must be attached separately"] }) },
};

export function targetAdapter(framework: Framework): TargetAdapterDescriptor {
  return TARGET_ADAPTERS[framework];
}

export function emitFromTargetAdapter(ir: CrossPlatformComponentIR, framework: Framework): TargetEmission {
  return targetAdapter(framework).emit(ir);
}
