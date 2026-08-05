/**
 * Typed gap catalogue for the FRT route layer.
 *
 * Every typed gap a route emitter or source extractor can report is registered
 * here exactly once. Severity is owned by this catalogue, not by the call site,
 * so a new unsupported semantic cannot be reported with an ad-hoc severity or,
 * worse, swallowed silently: `frtTypedGapDefinition` throws on an unregistered
 * code, and `test/frt-typed-gap-catalog.test.ts` asserts that the set of codes
 * literally present in the route sources equals the set registered here.
 */

export type FrtTypedGapSeverity = "WARNING" | "ERROR" | "CRITICAL";

export interface FrtTypedGapDefinition {
  /** Stable machine code. Never reused for a different meaning. */
  readonly code: string;
  /** Owned centrally; `blocking` is derived as `severity !== "WARNING"`. */
  readonly severity: FrtTypedGapSeverity;
  /** What the engine could not establish. */
  readonly summary: string;
  /** What a human has to decide or supply before this can stop being a gap. */
  readonly remediation: string;
}

const definitions: readonly FrtTypedGapDefinition[] = [
  // ---- directional route driver -------------------------------------------
  {
    code: "FRT_ROUTE_DIRECTION_INVALID",
    severity: "CRITICAL",
    summary: "The requested source/target pair is not a known non-self directional route.",
    remediation: "Select a source and target from the declared route stacks; self-routes are not conversions.",
  },
  {
    code: "FRT_TYPED_UI_IR_OR_SOURCE_INVALID",
    severity: "CRITICAL",
    summary: "The declared typed UI IR, or the source snapshot it references, failed exact validation.",
    remediation: "Supply a schema-exact frt-ui-ir.json whose sourceRefs digests match the submitted source bytes.",
  },
  {
    code: "FRT_TARGET_EMISSION_INVALID",
    severity: "CRITICAL",
    summary: "The emitted target project did not survive its own target-side validation.",
    remediation: "Fix the target emitter for this stack; never relax the target validator to make emission pass.",
  },

  // ---- Vue 3 source-of-truth extraction ------------------------------------
  {
    code: "FRT_VUE3_PACKAGE_MANIFEST_INVALID",
    severity: "CRITICAL",
    summary: "package.json is absent or not parseable, so the source cannot be proven to be Vue 3.",
    remediation: "Include the package.json that pins the Vue dependency in the source snapshot.",
  },
  {
    code: "FRT_VUE3_SOURCE_VERSION_NOT_EXACT",
    severity: "CRITICAL",
    summary: "The Vue dependency is missing, a range, or not a Vue 3 version.",
    remediation: "Pin an exact Vue 3 version (for example 3.5.39); ranges are not a versioned source contract.",
  },
  {
    code: "FRT_VUE3_SFC_CARDINALITY_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The snapshot does not contain exactly one Vue single-file component.",
    remediation: "Multi-component route graphs need an explicit component contract; they are not inferred.",
  },
  {
    code: "FRT_VUE3_SFC_PARSE_ERROR",
    severity: "CRITICAL",
    summary: "@vue/compiler-sfc reported a parse error for the source component.",
    remediation: "Fix the source SFC; the extractor never guesses past a parse error.",
  },
  {
    code: "FRT_VUE3_SCRIPT_MODE_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The component does not use exactly one <script setup lang=\"ts\"> block.",
    remediation: "This slice reads script setup only; Options API sources take the Vue 2 route.",
  },
  {
    code: "FRT_VUE3_TEMPLATE_MISSING",
    severity: "CRITICAL",
    summary: "The component has no parsed template AST to read the route contract from.",
    remediation: "Provide a template block; render functions are outside this extractor's evidence.",
  },
  {
    code: "FRT_VUE3_IMPORT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The script imports something other than the single Vue `ref` primitive.",
    remediation: "Any other import carries semantics this extractor cannot prove; map it explicitly.",
  },
  {
    code: "FRT_VUE3_REF_IMPORT_MISSING",
    severity: "CRITICAL",
    summary: "Reactive refs were used without an exact `ref` import from vue.",
    remediation: "Import ref explicitly so the reactive origin is provable from source.",
  },
  {
    code: "FRT_VUE3_BINDING_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A script binding is neither a string constant nor a numeric ref.",
    remediation: "Computed values, objects, and derived state need an explicit typed mapping decision.",
  },
  {
    code: "FRT_VUE3_SCRIPT_STATEMENT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A script statement lies outside the bounded counter-route slice.",
    remediation: "Extend the extractor deliberately, or declare the semantic out of scope; do not ignore it.",
  },
  {
    code: "FRT_VUE3_HANDLER_STATEMENT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "An event handler statement is not a deterministic integer state delta.",
    remediation: "Only `state.value += n`, `-= n`, `++`, and `--` are provable deltas in this slice.",
  },
  {
    code: "FRT_VUE3_ROUTE_ROOT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The template root is not a single <main> route element.",
    remediation: "This route slice describes one public root route rendered under a single <main>.",
  },
  {
    code: "FRT_VUE3_TEMPLATE_SHAPE_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The template does not present exactly the title/action/live-region triple this slice reads.",
    remediation: "Richer view shapes need IR schema growth first; they are not silently truncated.",
  },
  {
    code: "FRT_VUE3_TEMPLATE_ATTRIBUTE_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A template attribute or directive outside the certified slice was found.",
    remediation: "Each additional attribute is a semantic the target emitters must be taught explicitly.",
  },
  {
    code: "FRT_VUE3_TITLE_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "The route title could not be read from static text or a string constant.",
    remediation: "Bind the heading to a literal string constant, or accept that the title is not source-provable.",
  },
  {
    code: "FRT_VUE3_BUTTON_LABEL_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "The action label could not be read from static text or a string constant.",
    remediation: "Bind the button label to a literal string constant so the target can carry it faithfully.",
  },
  {
    code: "FRT_VUE3_COUNTER_STATE_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "The live region does not interpolate a single numeric ref, so initial state is unknown.",
    remediation: "Render the counter ref directly in the live region, or model the view state explicitly.",
  },
  {
    code: "FRT_VUE3_COUNTER_ACTION_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "The action does not resolve to one declared handler with one delta on the counter state.",
    remediation: "Bind @click to a zero-argument function whose only effect is a delta on the counter ref.",
  },
  {
    code: "FRT_VUE3_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE",
    severity: "CRITICAL",
    summary: "The accessibility contract (aria-label / aria-live) is not present in the source template.",
    remediation:
      "Add the accessibility attributes to the source. An accessibility contract that is not in the source cannot be "
      + "carried to a target; inventing one would fabricate an assurance the source never made.",
  },
  {
    code: "FRT_VUE3_LIVE_REGION_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The live region politeness is not the `polite` value this IR slice models.",
    remediation: "Extend the IR to carry other live-region modes before emitting them.",
  },
  {
    code: "FRT_VUE3_STYLE_CARDINALITY_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "More than one style block was found, so style order is not determined.",
    remediation: "Collapse to one style block, or add an ordered style contract to the IR.",
  },
  {
    code: "FRT_VUE3_ACCENT_COLOR_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "The style block is not the single `button { color: #rrggbb; }` design token this IR slice models.",
    remediation: "Grow the IR to a real design-token model before accepting broader stylesheets.",
  },
  {
    code: "FRT_DECLARED_IR_DIVERGES_FROM_SOURCE",
    severity: "CRITICAL",
    summary: "The declared frt-ui-ir.json asserts something the source does not say.",
    remediation:
      "Correct the declared IR or the source. A declared IR that outruns its source is exactly the failure mode "
      + "this cross-check exists to make impossible. Stack-neutral: every source stack with an extractor gets it.",
  },

  // ---- React source-of-truth extraction ------------------------------------
  {
    code: "FRT_REACT_PACKAGE_MANIFEST_INVALID",
    severity: "CRITICAL",
    summary: "package.json is absent or not parseable, so the source cannot be proven to be React.",
    remediation: "Include the package.json that pins the React dependency in the source snapshot.",
  },
  {
    code: "FRT_REACT_SOURCE_VERSION_NOT_EXACT",
    severity: "CRITICAL",
    summary: "The React dependency is missing or a range rather than an exact version.",
    remediation: "Pin an exact React version; ranges are not a versioned source contract.",
  },
  {
    code: "FRT_REACT_MODULE_CARDINALITY_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The snapshot does not contain exactly one React .tsx module.",
    remediation: "Multi-module route graphs need an explicit component contract; they are not inferred.",
  },
  {
    code: "FRT_REACT_PARSE_ERROR",
    severity: "CRITICAL",
    summary: "The TypeScript parser reported diagnostics for the React module.",
    remediation: "Fix the source module; the extractor never guesses past a parse error.",
  },
  {
    code: "FRT_REACT_IMPORT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The module imports something other than `useState` and one side-effect stylesheet.",
    remediation: "Any other import carries semantics this extractor cannot prove; map it explicitly.",
  },
  {
    code: "FRT_REACT_COMPONENT_CARDINALITY_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The module does not declare exactly one zero-prop function component.",
    remediation: "Props, multiple components, and non-function components need their own typed contract.",
  },
  {
    code: "FRT_REACT_BINDING_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A binding is neither a string constant nor an integer useState hook.",
    remediation: "Refs, memos, reducers, and derived values need an explicit typed mapping decision.",
  },
  {
    code: "FRT_REACT_STATEMENT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A statement lies outside the bounded counter-route slice.",
    remediation: "Extend the extractor deliberately, or declare the semantic out of scope; do not ignore it.",
  },
  {
    code: "FRT_REACT_ROUTE_ROOT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The component does not return a single <main> route element.",
    remediation: "This route slice describes one public root route rendered under a single <main>.",
  },
  {
    code: "FRT_REACT_TEMPLATE_SHAPE_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The JSX does not present exactly the title/action/live-region triple this slice reads.",
    remediation: "Richer view shapes need IR schema growth first; they are not silently truncated.",
  },
  {
    code: "FRT_REACT_TEMPLATE_ATTRIBUTE_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A JSX attribute or spread outside the certified slice was found.",
    remediation: "Each additional attribute is a semantic the target emitters must be taught explicitly.",
  },
  {
    code: "FRT_REACT_TITLE_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "The route title could not be read from static JSX text or a string constant.",
    remediation: "Bind the heading to a literal string constant, or accept that the title is not source-provable.",
  },
  {
    code: "FRT_REACT_BUTTON_LABEL_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "The action label could not be read from static JSX text or a string constant.",
    remediation: "Bind the button label to a literal string constant so the target can carry it faithfully.",
  },
  {
    code: "FRT_REACT_COUNTER_STATE_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "The live region does not render a single integer useState value, so initial state is unknown.",
    remediation: "Render the counter state directly in the live region, or model the view state explicitly.",
  },
  {
    code: "FRT_REACT_COUNTER_ACTION_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "onClick does not resolve to exactly one integer delta on the counter state.",
    remediation: "Use `setX(previous => previous + n)`, `setX(x + n)`, or a declared handler doing only that.",
  },
  {
    code: "FRT_REACT_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE",
    severity: "CRITICAL",
    summary: "The accessibility contract (aria-label / aria-live) is not present in the source JSX.",
    remediation:
      "Add the accessibility attributes to the source. An accessibility contract that is not in the source cannot "
      + "be carried to a target; inventing one would fabricate an assurance the source never made.",
  },
  {
    code: "FRT_REACT_LIVE_REGION_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The live region politeness is not the `polite` value this IR slice models.",
    remediation: "Extend the IR to carry other live-region modes before emitting them.",
  },
  {
    code: "FRT_REACT_STYLESHEET_CARDINALITY_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The snapshot does not contain exactly one stylesheet, so cascade order is undetermined.",
    remediation: "Collapse to one stylesheet, or add an ordered style contract to the IR.",
  },
  {
    code: "FRT_REACT_STYLESHEET_NOT_IMPORTED",
    severity: "CRITICAL",
    summary: "The component does not import the stylesheet, so the design token does not actually apply.",
    remediation: "Import the stylesheet from the component, or stop claiming its token in the IR.",
  },
  {
    code: "FRT_REACT_ACCENT_COLOR_NOT_DERIVABLE",
    severity: "CRITICAL",
    summary: "The stylesheet is not the single `button { color: #rrggbb; }` design token this IR slice models.",
    remediation: "Grow the IR to a real design-token model before accepting broader stylesheets.",
  },

  // ---- Vue 2 source-of-truth extraction ------------------------------------
  {
    code: "FRT_VUE2_PACKAGE_MANIFEST_INVALID", severity: "CRITICAL",
    summary: "The Vue 2 package manifest is absent or invalid.",
    remediation: "Include a valid package.json in the content-addressed source snapshot.",
  },
  {
    code: "FRT_VUE2_SOURCE_VERSION_NOT_EXACT", severity: "CRITICAL",
    summary: "The source does not pin an exact Vue 2 version.",
    remediation: "Pin the Vue dependency to an exact 2.x version; do not use a range.",
  },
  {
    code: "FRT_VUE2_SFC_CARDINALITY_UNSUPPORTED", severity: "CRITICAL",
    summary: "The bounded route does not contain exactly one Vue 2 SFC.",
    remediation: "Model a component graph before accepting a multi-SFC route.",
  },
  {
    code: "FRT_VUE2_SFC_PARSE_ERROR", severity: "CRITICAL",
    summary: "The Vue SFC parser rejected the Vue 2 source.",
    remediation: "Fix the SFC syntax; extraction never guesses past parser errors.",
  },
  {
    code: "FRT_VUE2_COMPONENT_MODE_UNSUPPORTED", severity: "CRITICAL",
    summary: "The component is not the bounded classic Options API form.",
    remediation: "Use one classic script and template, or add a separate typed component-mode adapter.",
  },
  {
    code: "FRT_VUE2_OPTIONS_API_UNSUPPORTED", severity: "CRITICAL",
    summary: "Options API features outside data and methods were found.",
    remediation: "Map props, computed, watch, mixins, lifecycle, and plugins explicitly before conversion.",
  },
  {
    code: "FRT_VUE2_STATE_ACTION_NOT_DERIVABLE", severity: "CRITICAL",
    summary: "Vue 2 state or its deterministic counter action could not be derived.",
    remediation: "Use literal data and one zero-argument method applying one integer state delta.",
  },
  {
    code: "FRT_VUE2_TEMPLATE_SHAPE_UNSUPPORTED", severity: "CRITICAL",
    summary: "The Vue 2 template is outside the bounded route component shape.",
    remediation: "Grow the typed UI IR before accepting a richer component tree.",
  },
  {
    code: "FRT_VUE2_TEMPLATE_SEMANTIC_UNSUPPORTED", severity: "CRITICAL",
    summary: "An unmodeled Vue 2 template attribute or directive was found.",
    remediation: "Add an explicit typed mapping for every additional template semantic.",
  },
  {
    code: "FRT_VUE2_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", severity: "CRITICAL",
    summary: "Required Vue 2 accessibility semantics are absent from source.",
    remediation: "Declare the route/action labels and live region in the source template.",
  },
  {
    code: "FRT_VUE2_LIVE_REGION_UNSUPPORTED", severity: "CRITICAL",
    summary: "The Vue 2 live-region mode cannot be carried by this IR slice.",
    remediation: "Extend the IR before accepting a mode other than polite.",
  },
  {
    code: "FRT_VUE2_STYLE_UNSUPPORTED", severity: "CRITICAL",
    summary: "The Vue 2 style contract cannot be reduced to the bounded accent token.",
    remediation: "Define an ordered design-token model before accepting broader CSS.",
  },

  // ---- WeChat Mini Program source-of-truth extraction ----------------------
  {
    code: "FRT_MINIPROGRAM_PROJECT_PROFILE_INVALID", severity: "CRITICAL",
    summary: "The Mini Program profile does not prove an exact base-library source version.",
    remediation: "Provide a valid project.config.json with compileType and exact libVersion.",
  },
  {
    code: "FRT_MINIPROGRAM_PAGE_CARDINALITY_UNSUPPORTED", severity: "CRITICAL",
    summary: "The bounded Mini Program route does not contain one WXML, Page script, and WXSS.",
    remediation: "Model the page/component graph before accepting a multi-page snapshot.",
  },
  {
    code: "FRT_MINIPROGRAM_WXML_PARSE_ERROR", severity: "CRITICAL",
    summary: "The structural WXML parser rejected the page source.",
    remediation: "Fix tag/attribute structure; the extractor never repairs or guesses WXML.",
  },
  {
    code: "FRT_MINIPROGRAM_WXML_SEMANTIC_UNSUPPORTED", severity: "CRITICAL",
    summary: "The WXML carries nodes, bindings, attributes, or events outside the bounded grammar.",
    remediation: "Grow the typed UI IR and target emitters before accepting the extra semantic.",
  },
  {
    code: "FRT_MINIPROGRAM_ACCESSIBILITY_CONTRACT_NOT_IN_SOURCE", severity: "CRITICAL",
    summary: "Required Mini Program accessibility semantics are absent from WXML.",
    remediation: "Declare the main role, labels, and live region in WXML source.",
  },
  {
    code: "FRT_MINIPROGRAM_LIVE_REGION_UNSUPPORTED", severity: "CRITICAL",
    summary: "The Mini Program live-region mode cannot be carried by this IR slice.",
    remediation: "Extend the IR before accepting a mode other than polite.",
  },
  {
    code: "FRT_MINIPROGRAM_STATE_ACTION_NOT_DERIVABLE", severity: "CRITICAL",
    summary: "Page data or its setData counter transition could not be derived.",
    remediation: "Use literal Page data and one deterministic setData integer delta.",
  },
  {
    code: "FRT_MINIPROGRAM_STYLE_UNSUPPORTED", severity: "CRITICAL",
    summary: "The WXSS cannot be reduced to the bounded accent token.",
    remediation: "Define an ordered Mini Program design-token model before accepting broader styles.",
  },

  // ---- ArkUI source-of-truth extraction ------------------------------------
  {
    code: "FRT_ARKUI_PROFILE_INVALID", severity: "CRITICAL",
    summary: "The ArkUI build profile does not pin an API version.",
    remediation: "Provide a valid build-profile.json5 with one numeric apiVersion.",
  },
  {
    code: "FRT_ARKUI_MODULE_CARDINALITY_UNSUPPORTED", severity: "CRITICAL",
    summary: "The bounded ArkUI route does not contain exactly one ArkTS module.",
    remediation: "Model the ArkUI page/component graph before accepting multiple modules.",
  },
  {
    code: "FRT_ARKUI_PARSE_ERROR", severity: "CRITICAL",
    summary: "The balanced ArkTS tokenizer rejected the source.",
    remediation: "Fix strings, comments, and delimiters before extraction.",
  },
  {
    code: "FRT_ARKUI_CONTRACT_NOT_DERIVABLE", severity: "CRITICAL",
    summary: "ArkUI state, action, widgets, accessibility, or styling could not be derived.",
    remediation: "Supply every bounded contract field explicitly in the ArkTS component.",
  },
  {
    code: "FRT_ARKUI_SEMANTIC_UNSUPPORTED", severity: "CRITICAL",
    summary: "The ArkTS module contains semantics outside the exact bounded component grammar.",
    remediation: "Add a typed mapping and negative tests before accepting the additional ArkUI syntax.",
  },

  // ---- Flutter source-of-truth extraction ----------------------------------
  {
    code: "FRT_FLUTTER_VERSION_PROFILE_INVALID", severity: "CRITICAL",
    summary: "The Flutter source does not pin an exact SDK version.",
    remediation: "Provide a valid .fvmrc with one exact Flutter version.",
  },
  {
    code: "FRT_FLUTTER_PUBSPEC_INVALID", severity: "CRITICAL",
    summary: "The pubspec does not declare the Flutter SDK dependency.",
    remediation: "Include a valid Flutter SDK dependency in pubspec.yaml.",
  },
  {
    code: "FRT_FLUTTER_MODULE_CARDINALITY_UNSUPPORTED", severity: "CRITICAL",
    summary: "The bounded Flutter route does not contain exactly one application Dart module.",
    remediation: "Model the widget/module graph before accepting multiple application modules.",
  },
  {
    code: "FRT_FLUTTER_PARSE_ERROR", severity: "CRITICAL",
    summary: "The balanced Dart tokenizer rejected the source.",
    remediation: "Fix strings, comments, and delimiters before extraction.",
  },
  {
    code: "FRT_FLUTTER_CONTRACT_NOT_DERIVABLE", severity: "CRITICAL",
    summary: "Flutter state, action, widgets, semantics, or styling could not be derived.",
    remediation: "Supply every bounded contract field explicitly in the Dart widget tree.",
  },
  {
    code: "FRT_FLUTTER_SEMANTIC_UNSUPPORTED", severity: "CRITICAL",
    summary: "The Dart module contains semantics outside the exact bounded widget grammar.",
    remediation: "Add a typed mapping and negative tests before accepting the additional Dart syntax.",
  },

  // ---- Vue 3 -> React vertical slice ---------------------------------------
  {
    code: "FRT_VUE3_VERSION_UNRESOLVED",
    severity: "CRITICAL",
    summary: "package.json does not bind an explicit Vue 3 dependency version.",
    remediation: "Pin the Vue 3 dependency so the source stack version is provable.",
  },
  {
    code: "FRT_VUE_PACKAGE_MANIFEST_INVALID",
    severity: "CRITICAL",
    summary: "package.json is missing or unparseable for the Vue 3 -> React route.",
    remediation: "Include a valid package.json in the source snapshot.",
  },
  {
    code: "FRT_VUE_SFC_CARDINALITY_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "The Vue 3 -> React slice requires exactly one Vue SFC.",
    remediation: "Multi-component graph conversion remains an explicit, separate contract.",
  },
  {
    code: "FRT_VUE_SFC_PARSE_ERROR",
    severity: "CRITICAL",
    summary: "@vue/compiler-sfc reported a parse error.",
    remediation: "Fix the source SFC before conversion.",
  },
  {
    code: "FRT_VUE_TEMPLATE_MISSING",
    severity: "CRITICAL",
    summary: "A parsed Vue template AST is required.",
    remediation: "Provide a template block.",
  },
  {
    code: "FRT_VUE_SCRIPT_MODE_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "Exactly one <script setup> block and no classic script block is required.",
    remediation: "Split or migrate the source component first.",
  },
  {
    code: "FRT_VUE_TYPESCRIPT_REQUIRED",
    severity: "CRITICAL",
    summary: "The script setup block must be TypeScript.",
    remediation: "Use lang=\"ts\" so declarations carry types into the React target.",
  },
  {
    code: "FRT_VUE_STYLE_CARDINALITY_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "Multiple style blocks require an ordered style contract.",
    remediation: "Collapse to one style block, or define the cascade order explicitly.",
  },
  {
    code: "FRT_VUE_SCOPED_STYLE_COMPILE_ERROR",
    severity: "CRITICAL",
    summary: "Scoped style compilation failed.",
    remediation: "Fix the scoped stylesheet; scope attributes are never applied blindly.",
  },
  {
    code: "FRT_VUE_EXTERNAL_IMPORT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A non-Vue import requires an explicit target adapter.",
    remediation: "Declare how the imported module maps into the React target.",
  },
  {
    code: "FRT_VUE_COMPOSITION_API_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "Only the Vue `ref` composition primitive is supported by this slice.",
    remediation: "computed/watch/reactive need explicit React equivalents with their own evidence.",
  },
  {
    code: "FRT_VUE_VARIABLE_PATTERN_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "Destructuring or uninitialized declarations require a typed mapping decision.",
    remediation: "Use simple initialized identifier declarations in this slice.",
  },
  {
    code: "FRT_VUE_REF_ARITY_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A ref does not have exactly one deterministic initializer.",
    remediation: "Give every ref one literal initial value.",
  },
  {
    code: "FRT_VUE_REF_IMPORT_MISSING",
    severity: "CRITICAL",
    summary: "Reactive refs were found without an exact Vue ref import.",
    remediation: "Import ref explicitly.",
  },
  {
    code: "FRT_VUE_FUNCTION_STATEMENT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A function body statement lies outside the certified vertical slice.",
    remediation: "Extend the converter deliberately for the statement form.",
  },
  {
    code: "FRT_VUE_SCRIPT_STATEMENT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A top-level script statement requires an explicit semantic adapter.",
    remediation: "Map the statement form explicitly before conversion.",
  },
  {
    code: "FRT_VUE_INTERPOLATION_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "Template interpolation must be a side-effect-free identifier path.",
    remediation: "Move expression logic into a named binding.",
  },
  {
    code: "FRT_VUE_TEMPLATE_NODE_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A Vue template node type is unsupported.",
    remediation: "Teach the renderer the node type explicitly.",
  },
  {
    code: "FRT_VUE_COMPONENT_OR_SLOT_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A child component or slot requires an explicit component contract.",
    remediation: "Declare the component mapping before converting the parent.",
  },
  {
    code: "FRT_VUE_DIRECTIVE_MODIFIER_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "Directive modifiers are not silently approximated.",
    remediation: "Map each modifier to its explicit React behaviour.",
  },
  {
    code: "FRT_VUE_DIRECTIVE_UNSUPPORTED",
    severity: "CRITICAL",
    summary: "A directive has no explicit React semantic mapping.",
    remediation: "Add the mapping deliberately, with a test that proves the behaviour.",
  },
];

const catalogue: ReadonlyMap<string, FrtTypedGapDefinition> = new Map(
  definitions.map(definition => [definition.code, Object.freeze(definition)]),
);

if (catalogue.size !== definitions.length) {
  throw new Error("the typed gap catalogue contains duplicate codes");
}

export const frtTypedGapCodes: readonly string[] = Object.freeze(
  [...catalogue.keys()].sort(),
);

/** Resolve a typed gap definition. Throws for an unregistered code by design. */
export function frtTypedGapDefinition(code: string): FrtTypedGapDefinition {
  const definition = catalogue.get(code);
  if (!definition) {
    throw new Error(
      `typed gap code ${code} is not registered in the FRT typed gap catalogue; `
      + "register it with an explicit severity and remediation before reporting it",
    );
  }
  return definition;
}

export function frtTypedGapCatalogue(): readonly FrtTypedGapDefinition[] {
  return definitions;
}
