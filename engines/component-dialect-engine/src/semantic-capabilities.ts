import type { Framework } from "./models";

/**
 * Semantic features that exist outside the small automatic ComponentDef
 * proof boundary.  These names are intentionally framework-neutral: a
 * React `useEffect` and a Vue `onMounted` can both become an ASYNC_EFFECT,
 * while the target adapter remains responsible for choosing a lifecycle
 * primitive and proving cleanup/cancellation behaviour.
 */
export type SourceSemanticFeatureKind =
  | "EXTERNAL_HOOK"
  | "ASYNC_EFFECT"
  | "NETWORK_RESOURCE"
  | "TIMER_RESOURCE"
  | "SUBSCRIPTION_RESOURCE"
  | "STORAGE_RESOURCE"
  | "NATIVE_RESOURCE"
  | "WORKER_RESOURCE"
  | "OBJECT_STATE"
  | "LITERAL_UNION_TYPE"
  | "UNKNOWN_OR_INCOMPATIBLE_TYPE"
  | "MAP_COLLECTION"
  | "SET_COLLECTION"
  | "DERIVED_COLLECTION"
  | "SLOT_PROJECTION"
  | "COMPONENT_COMPOSITION"
  | "HTML_SEMANTIC"
  | "TABLE_SEMANTIC"
  | "DISCLOSURE_SEMANTIC"
  | "SVG_SEMANTIC"
  | "DOCUMENT_ROOT_SEMANTIC"
  | "CSS_MODULE"
  | "UNMODELED_SOURCE_SEMANTIC";

export interface SourceSemanticRange {
  start: number;
  end: number;
  startLine: number;
  startColumn: number;
  endLine: number;
  endColumn: number;
}

export interface SourceSemanticFeature {
  id: string;
  kind: SourceSemanticFeatureKind;
  detail: string;
  sourceRange: SourceSemanticRange;
  /** A bounded diagnostic excerpt. It is evidence for review, never input
   * to an emitter and never executed. */
  sourceExcerpt: string;
}

export type TargetSemanticMode = "NATIVE" | "ADAPTER" | "HAND_PORTED" | "BLOCKED";

export interface TargetSemanticDecision {
  featureId: string;
  featureKind: SourceSemanticFeatureKind;
  mode: TargetSemanticMode;
  reason: string;
  requiredEvidence: string[];
}

const WEB_TARGETS = new Set<Framework>(["react", "typescript", "vue3", "vue2", "angular", "svelte"]);
const NATIVE_TARGETS = new Set<Framework>(["react-native", "miniprogram", "arkui", "flutter"]);

function decision(
  feature: SourceSemanticFeature,
  mode: TargetSemanticMode,
  reason: string,
  requiredEvidence: string[],
): TargetSemanticDecision {
  return { featureId: feature.id, featureKind: feature.kind, mode, reason, requiredEvidence };
}

/**
 * Exact per-feature target decision.  This does not claim that an adapter
 * has run; ADAPTER means a typed adapter implementation and its named
 * evidence are required before the component can leave HAND_PORTED/BLOCKED.
 */
export function decideTargetSemanticFeature(
  target: Framework,
  feature: SourceSemanticFeature,
): TargetSemanticDecision {
  const web = WEB_TARGETS.has(target);
  const native = NATIVE_TARGETS.has(target);

  switch (feature.kind) {
    case "EXTERNAL_HOOK":
      return decision(feature, "BLOCKED",
        `${target} cannot infer the contract of an application-defined Hook`,
        ["hook-adapter-contract", "target-build", "runtime-journey", "independent-review"]);
    case "ASYNC_EFFECT":
      return decision(feature, "ADAPTER",
        `${target} requires an explicit lifecycle, ordering, cancellation and error-state adapter`,
        ["effect-adapter", "cancellation-cleanup", "target-build", "runtime-journey"]);
    case "NETWORK_RESOURCE":
      return decision(feature, "ADAPTER",
        `${target} requires an authenticated network/client adapter with cancellation and failure semantics`,
        ["network-adapter", "cancellation-cleanup", "negative-runtime", "independent-review"]);
    case "TIMER_RESOURCE":
      return decision(feature, "ADAPTER",
        `${target} requires target lifecycle ownership for timer creation and cleanup`,
        ["timer-adapter", "cleanup-runtime", "target-build"]);
    case "SUBSCRIPTION_RESOURCE":
      return decision(feature, "ADAPTER",
        `${target} requires symmetric subscribe/unsubscribe behaviour in its lifecycle`,
        ["subscription-adapter", "cleanup-runtime", "negative-runtime"]);
    case "STORAGE_RESOURCE":
      return decision(feature, "ADAPTER",
        `${target} requires a storage namespace, serialization and failure-policy adapter`,
        ["storage-adapter", "migration-fixture", "negative-runtime"]);
    case "NATIVE_RESOURCE":
    case "WORKER_RESOURCE":
      return decision(feature, native ? "ADAPTER" : "HAND_PORTED",
        `${target} needs a platform-owned resource implementation; source API identity is not portable`,
        ["platform-resource-adapter", "cleanup-runtime", "device-or-browser", "independent-review"]);
    case "OBJECT_STATE":
      return decision(feature, web ? "NATIVE" : "ADAPTER",
        web
          ? `${target} can represent closed object/array state natively once its exact type is resolved`
          : `${target} needs generated value/update bindings for structured state`,
        web ? ["target-build", "state-journey"] : ["state-adapter", "target-build", "device-journey"]);
    case "LITERAL_UNION_TYPE":
      return decision(feature, web ? "NATIVE" : "ADAPTER",
        web
          ? `${target} can preserve a closed literal union in generated type/runtime guards`
          : `${target} requires an enum/sealed-value adapter and unknown-value policy`,
        ["typecheck", "unknown-value-negative-test"]);
    case "UNKNOWN_OR_INCOMPATIBLE_TYPE":
      return decision(feature, "BLOCKED",
        `${target} cannot safely lower an unresolved or incompatible source type`,
        ["resolved-data-contract", "negative-type-corpus", "independent-review"]);
    case "MAP_COLLECTION":
    case "SET_COLLECTION":
    case "DERIVED_COLLECTION":
      return decision(feature, "ADAPTER",
        `${target} requires deterministic collection ordering, identity and mutation semantics`,
        ["collection-adapter", "ordering-fixture", "identity-fixture", "target-build"]);
    case "SLOT_PROJECTION":
      return decision(feature,
        target === "react" || target === "typescript" || target === "vue3" || target === "vue2" || target === "angular" || target === "svelte"
          ? "ADAPTER" : "HAND_PORTED",
        `${target} must preserve parent/child evaluation, fallback and scope ownership`,
        ["slot-adapter", "projection-journey", "target-build", "independent-review"]);
    case "COMPONENT_COMPOSITION":
      return decision(feature, "ADAPTER",
        `${target} requires an exact child identity, prop and event binding adapter`,
        ["component-registry", "target-build", "composition-journey"]);
    case "TABLE_SEMANTIC":
      return decision(feature, web ? "NATIVE" : "HAND_PORTED",
        web
          ? `${target} preserves the table accessibility tree with native document elements`
          : `${target} has no general native table semantic equivalent`,
        web ? ["target-build", "accessibility-tree"] : ["approved-table-design", "device-journey", "accessibility-review"]);
    case "DISCLOSURE_SEMANTIC":
      return decision(feature, web ? "NATIVE" : "ADAPTER",
        web
          ? `${target} can preserve native disclosure semantics`
          : `${target} needs expanded state, focus and accessibility actions`,
        ["target-build", "keyboard-or-device-journey", "accessibility-review"]);
    case "SVG_SEMANTIC":
      return decision(feature, web ? "NATIVE" : "HAND_PORTED",
        web
          ? `${target} can retain an inline SVG tree and accessible naming`
          : `${target} needs an approved vector asset/component strategy`,
        web ? ["target-build", "visual-regression", "accessibility-review"] : ["approved-vector-adapter", "device-visual", "independent-review"]);
    case "DOCUMENT_ROOT_SEMANTIC":
      return decision(feature,
        target === "react" || target === "typescript" ? "ADAPTER" : "HAND_PORTED",
        `${target} must map document ownership, metadata and hydration outside an ordinary component boundary`,
        ["application-shell-adapter", "target-build", "startup-runtime", "independent-review"]);
    case "HTML_SEMANTIC":
      return decision(feature, web ? "NATIVE" : "ADAPTER",
        web
          ? `${target} can retain the source document semantic element`
          : `${target} requires an accessibility-preserving native container mapping`,
        ["target-build", "accessibility-tree", ...(native ? ["device-journey"] : [])]);
    case "CSS_MODULE":
      return decision(feature,
        target === "react" || target === "typescript" ? "NATIVE" : "ADAPTER",
        `${target} must preserve class-token identity and the bound stylesheet bytes`,
        ["stylesheet-digest", "target-build", "visual-regression"]);
    case "UNMODELED_SOURCE_SEMANTIC":
      return decision(feature, "BLOCKED",
        `${target} has no typed lowering for this explicitly captured source construct`,
        ["typed-ir-extension", "target-adapter", "negative-corpus", "independent-review"]);
  }
}
