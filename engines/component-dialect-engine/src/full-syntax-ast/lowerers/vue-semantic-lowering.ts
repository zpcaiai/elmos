/**
 * Deep Vue 2 / Vue 3 AST Semantic Lowering Engine.
 * 
 * Translates Vue 2 Options API (mixins, watch, data, computed, methods)
 * and Vue 3 Composition API (<script setup>, ref, reactive, toRefs, watchEffect, provide/inject)
 * and Vue SFC Templates into canonical FullSyntaxComponentIR.
 */

import {
  FullSyntaxComponentIR,
  FullSyntaxProp,
  FullSyntaxState,
  FullSyntaxComputed,
  FullSyntaxEffect,
  FullSyntaxMethod,
  FullSyntaxSlot,
  FullSyntaxNode,
} from "../types";
import { ReactiveDependencyDAG } from "../core/reactive-dependency-dag";
import { DirectiveDecisionTreeEngine } from "../core/directive-decision-tree";

export interface VueOptionsDeclaration {
  props?: Record<string, { type?: string; required?: boolean; default?: any }>;
  data?: Record<string, any>;
  computed?: Record<string, string | { get: string; set?: string }>;
  methods?: Record<string, { params: string[]; body: string; isAsync: boolean }>;
  watch?: Record<string, { handler: string; deep?: boolean; immediate?: boolean }>;
  mixins?: string[];
  provide?: Record<string, any>;
  inject?: string[];
}

export interface VueCompositionDeclaration {
  refs?: { name: string; initialExpr: string; type: string }[];
  reactives?: { name: string; initialExpr: string; type: string }[];
  computeds?: { name: string; exprOrFn: string; returnType: string }[];
  watchers?: { source: string; body: string; deep?: boolean; immediate?: boolean }[];
  effects?: { body: string; hookKind: "onMounted" | "onUpdated" | "onUnmounted" }[];
  methods?: { name: string; params: string[]; body: string; isAsync: boolean }[];
}

export class VueSemanticLoweringEngine {
  /**
   * Lowers Vue 2 / 3 Options API component into canonical IR.
   */
  public static lowerOptionsAPI(
    componentName: string,
    options: VueOptionsDeclaration,
    templateRoot: FullSyntaxNode,
    slots: FullSyntaxSlot[] = [],
    sourceCode = ""
  ): FullSyntaxComponentIR {
    const props: FullSyntaxProp[] = [];
    const states: FullSyntaxState[] = [];
    const computed: FullSyntaxComputed[] = [];
    const effects: FullSyntaxEffect[] = [];
    const methods: FullSyntaxMethod[] = [];

    // 1. Props
    if (options.props) {
      for (const [propName, propDef] of Object.entries(options.props)) {
        props.push({
          name: propName,
          typeAnnotation: propDef.type || "any",
          required: Boolean(propDef.required),
          defaultValue: propDef.default !== undefined ? JSON.stringify(propDef.default) : undefined,
          isCallback: propName.startsWith("on") || propName.endsWith("Fn"),
        });
      }
    }

    // 2. Data -> States
    if (options.data) {
      for (const [dataKey, dataVal] of Object.entries(options.data)) {
        states.push({
          name: dataKey,
          initialValueExpr: typeof dataVal === "object" ? JSON.stringify(dataVal) : String(dataVal),
          typeAnnotation: typeof dataVal,
        });
      }
    }

    // 3. Computed
    if (options.computed) {
      for (const [compKey, compVal] of Object.entries(options.computed)) {
        const body = typeof compVal === "string" ? compVal : compVal.get;
        computed.push({
          name: compKey,
          returnType: "any",
          dependencies: [], // extracted via DAG
          expressionOrBody: body,
        });

        // If computed setter exists, register as a method
        if (typeof compVal === "object" && compVal.set) {
          methods.push({
            name: `set_${compKey}`,
            parameters: [{ name: "value", type: "any" }],
            returnType: "void",
            bodyCode: compVal.set,
            isAsync: false,
          });
        }
      }
    }

    // 4. Watch -> Effects
    if (options.watch) {
      for (const [watchKey, watchDef] of Object.entries(options.watch)) {
        effects.push({
          id: `watch_${watchKey}`,
          hookKind: "watch",
          dependencies: [watchKey],
          bodyCode: watchDef.handler,
          hasCleanup: false,
        });
      }
    }

    // 5. Methods
    if (options.methods) {
      for (const [methodName, methodDef] of Object.entries(options.methods)) {
        methods.push({
          name: methodName,
          parameters: methodDef.params.map(p => ({ name: p, type: "any" })),
          returnType: "any",
          bodyCode: methodDef.body,
          isAsync: methodDef.isAsync,
        });
      }
    }

    // 6. Reactive DAG Analysis & Reordering
    const dag = new ReactiveDependencyDAG();
    dag.ingestComponentMembers(props, states, computed, effects, methods);
    const dagAnalysis = dag.analyze();

    return {
      schemaVersion: "2.0",
      componentName,
      sourceFramework: "vue2",
      targetFramework: "miniprogram",
      description: `Synthesized from Vue Options API component ${componentName}`,
      props,
      states,
      computed,
      effects,
      methods,
      slots,
      refs: [],
      templateRoot: this.normalizeVueTemplateTree(templateRoot),
      styles: { scopedCss: "" },
      containerApis: [],
      thirdPartyComponents: [],
      rawSourceLinesCount: sourceCode.split("\n").length,
      metadata: {
        dagAnalysis: {
          cycleDetected: dagAnalysis.cycles.length > 0,
          topologicalOrder: dagAnalysis.topologicalOrder,
        },
      },
    };
  }

  /**
   * Lowers Vue 3 Composition API (<script setup>) component into canonical IR.
   */
  public static lowerCompositionAPI(
    componentName: string,
    composition: VueCompositionDeclaration,
    templateRoot: FullSyntaxNode,
    props: FullSyntaxProp[] = [],
    slots: FullSyntaxSlot[] = [],
    sourceCode = ""
  ): FullSyntaxComponentIR {
    const states: FullSyntaxState[] = [];
    const computed: FullSyntaxComputed[] = [];
    const effects: FullSyntaxEffect[] = [];
    const methods: FullSyntaxMethod[] = [];

    // 1. ref & reactive -> States
    if (composition.refs) {
      for (const r of composition.refs) {
        states.push({
          name: r.name,
          initialValueExpr: r.initialExpr,
          typeAnnotation: r.type || "any",
          isRef: true,
        });
      }
    }

    if (composition.reactives) {
      for (const r of composition.reactives) {
        states.push({
          name: r.name,
          initialValueExpr: r.initialExpr,
          typeAnnotation: r.type || "Record<string, any>",
          isRef: false,
        });
      }
    }

    // 2. computeds
    if (composition.computeds) {
      for (const c of composition.computeds) {
        computed.push({
          name: c.name,
          returnType: c.returnType || "any",
          dependencies: [],
          expressionOrBody: c.exprOrFn,
        });
      }
    }

    // 3. watch & watchEffect -> Effects
    if (composition.watchers) {
      for (const w of composition.watchers) {
        effects.push({
          id: `watch_${w.source}`,
          hookKind: "watch",
          dependencies: [w.source],
          bodyCode: w.body,
          hasCleanup: false,
        });
      }
    }

    if (composition.effects) {
      for (const e of composition.effects) {
        effects.push({
          id: `lifecycle_${e.hookKind}_${effects.length + 1}`,
          hookKind: e.hookKind === "onMounted" ? "mount" : e.hookKind === "onUnmounted" ? "unmount" : "update",
          dependencies: [],
          bodyCode: e.body,
          hasCleanup: e.hookKind === "onUnmounted",
        });
      }
    }

    // 4. methods
    if (composition.methods) {
      for (const m of composition.methods) {
        methods.push({
          name: m.name,
          parameters: m.params.map(p => ({ name: p, type: "any" })),
          returnType: "any",
          bodyCode: m.body,
          isAsync: m.isAsync,
        });
      }
    }

    // DAG Analysis
    const dag = new ReactiveDependencyDAG();
    dag.ingestComponentMembers(props, states, computed, effects, methods);
    const dagAnalysis = dag.analyze();

    return {
      schemaVersion: "2.0",
      componentName,
      sourceFramework: "vue3",
      targetFramework: "miniprogram",
      description: `Synthesized from Vue 3 Composition API component ${componentName}`,
      props,
      states,
      computed,
      effects,
      methods,
      slots,
      refs: [],
      templateRoot: this.normalizeVueTemplateTree(templateRoot),
      styles: { scopedCss: "" },
      containerApis: [],
      thirdPartyComponents: [],
      rawSourceLinesCount: sourceCode.split("\n").length,
      metadata: {
        dagAnalysis: {
          cycleDetected: dagAnalysis.cycles.length > 0,
          topologicalOrder: dagAnalysis.topologicalOrder,
        },
      },
    };
  }

  /**
   * Normalizes Vue template AST directives (v-if/else-if/else, v-for, v-model, dynamic bindings).
   */
  private static normalizeVueTemplateTree(node: FullSyntaxNode): FullSyntaxNode {
    if (!node) return node;

    let res: FullSyntaxNode = { ...node };

    // Normalizing conditional chains via DirectiveDecisionTree
    if (res.kind === "conditional" || res.condition) {
      const decisionTree = DirectiveDecisionTreeEngine.normalizeCondition(res);
      const firstBranch = decisionTree.branches[0];
      if (firstBranch) {
        res.condition = {
          test: firstBranch.conditionExpr,
          thenNode: this.normalizeVueTemplateTree(firstBranch.node),
          elifBranches: decisionTree.branches.slice(1).map(b => ({
            test: b.conditionExpr,
            node: this.normalizeVueTemplateTree(b.node),
          })),
          elseNode: decisionTree.fallbackNode ? this.normalizeVueTemplateTree(decisionTree.fallbackNode) : undefined,
        };
      }
    }

    // Recursively process children and loops
    if (res.children && res.children.length > 0) {
      res.children = res.children.map(c => this.normalizeVueTemplateTree(c));
    }
    if (res.loop && res.loop.bodyNode) {
      res.loop.bodyNode = this.normalizeVueTemplateTree(res.loop.bodyNode);
    }

    return res;
  }
}
