/**
 * Deep Svelte 4 / Svelte 5 AST Semantic Lowering Engine.
 * 
 * Translates Svelte 5 Runes ($state, $derived, $effect, $props, $bindable)
 * and Svelte 4 legacy reactive declarations ($: doubled = count * 2, stores $store)
 * and Svelte Templates ({#if}, {#each}, {#await}, bind:value, on:click)
 * into canonical FullSyntaxComponentIR.
 */

import {
  FullSyntaxComponentIR,
  FullSyntaxProp,
  FullSyntaxState,
  FullSyntaxComputed,
  FullSyntaxEffect,
  FullSyntaxMethod,
  FullSyntaxNode,
} from "../types";
import { ReactiveDependencyDAG } from "../core/reactive-dependency-dag";
import { DirectiveDecisionTreeEngine } from "../core/directive-decision-tree";

export interface SvelteModuleFacts {
  componentName: string;
  isSvelte5: boolean;
  props: { name: string; type: string; defaultValue?: string; isBindable?: boolean }[];
  stateRunes: { name: string; initialExpr: string; type: string }[];
  derivedRunes: { name: string; computationExpr: string; type: string }[];
  effectRunes: { id: string; bodyCode: string }[];
  legacyReactiveStatements: { targetVar?: string; exprOrBody: string }[];
  stores: { name: string; initialValueExpr: string }[];
  methods: { name: string; params: { name: string; type: string }[]; returnType: string; body: string; isAsync: boolean }[];
}

export class SvelteSemanticLoweringEngine {
  /**
   * Lowers Svelte 4 / Svelte 5 module facts and template into Universal Component IR.
   */
  public static lowerSvelteComponent(
    facts: SvelteModuleFacts,
    templateRoot: FullSyntaxNode,
    sourceCode = ""
  ): FullSyntaxComponentIR {
    const props: FullSyntaxProp[] = [];
    const states: FullSyntaxState[] = [];
    const computed: FullSyntaxComputed[] = [];
    const effects: FullSyntaxEffect[] = [];
    const methods: FullSyntaxMethod[] = [];

    // 1. Props ($props() in Svelte 5 or export let in Svelte 4)
    for (const p of facts.props) {
      props.push({
        name: p.name,
        typeAnnotation: p.type || "any",
        required: p.defaultValue === undefined,
        defaultValue: p.defaultValue,
        isCallback: p.name.startsWith("on") || p.name.endsWith("Fn"),
      });
    }

    // 2. States ($state() or let x = ...)
    for (const s of facts.stateRunes) {
      states.push({
        name: s.name,
        initialValueExpr: s.initialExpr || "null",
        typeAnnotation: s.type || "any",
        isRef: false,
      });
    }

    // 3. Derived ($derived() or $derived.by()) -> Computed
    for (const d of facts.derivedRunes) {
      computed.push({
        name: d.name,
        returnType: d.type || "any",
        dependencies: [],
        expressionOrBody: d.computationExpr,
      });
    }

    // 4. Effects ($effect()) -> Effects
    for (const e of facts.effectRunes) {
      effects.push({
        id: e.id,
        hookKind: "effect",
        dependencies: [],
        bodyCode: e.bodyCode,
        hasCleanup: e.bodyCode.includes("return"),
      });
    }

    // 5. Legacy Svelte 4 Reactive Declarations ($:)
    for (let i = 0; i < facts.legacyReactiveStatements.length; i++) {
      const stmt = facts.legacyReactiveStatements[i];
      if (!stmt) continue;
      if (stmt.targetVar) {
        // Variable assignment: $: doubled = count * 2 -> Computed property
        computed.push({
          name: stmt.targetVar,
          returnType: "any",
          dependencies: [],
          expressionOrBody: stmt.exprOrBody,
        });
      } else {
        // Side effect block: $: { console.log(count); } -> Effect
        effects.push({
          id: `svelte_effect_${i + 1}`,
          hookKind: "effect",
          dependencies: [],
          bodyCode: stmt.exprOrBody,
          hasCleanup: false,
        });
      }
    }

    // 6. Stores ($store subscription)
    for (const st of facts.stores) {
      states.push({
        name: st.name,
        initialValueExpr: st.initialValueExpr,
        typeAnnotation: "any",
      });
    }

    // 7. Methods
    for (const m of facts.methods) {
      methods.push({
        name: m.name,
        parameters: m.params,
        returnType: m.returnType,
        bodyCode: m.body,
        isAsync: m.isAsync,
      });
    }

    // 8. DAG Analysis and Topological Ordering
    const dag = new ReactiveDependencyDAG();
    dag.ingestComponentMembers(props, states, computed, effects, methods);
    const dagAnalysis = dag.analyze();

    return {
      schemaVersion: "2.0",
      componentName: facts.componentName,
      sourceFramework: "svelte",
      targetFramework: "miniprogram",
      description: `Synthesized from Svelte ${facts.isSvelte5 ? "5" : "4"} component ${facts.componentName}`,
      props,
      states,
      computed,
      effects,
      methods,
      slots: [],
      refs: [],
      templateRoot: this.lowerSvelteTemplateTree(templateRoot),
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
   * Normalizes Svelte template syntax ({#if}, {:else if}, {#each}, {#await}).
   */
  private static lowerSvelteTemplateTree(node: FullSyntaxNode): FullSyntaxNode {
    if (!node) return node;

    let res: FullSyntaxNode = { ...node };

    // Normalize Svelte {#if} blocks via DecisionTree
    if (res.kind === "conditional" || res.condition) {
      const decisionTree = DirectiveDecisionTreeEngine.normalizeCondition(res);
      const firstBranch = decisionTree.branches[0];
      if (firstBranch) {
        res.condition = {
          test: firstBranch.conditionExpr,
          thenNode: this.lowerSvelteTemplateTree(firstBranch.node),
          elifBranches: decisionTree.branches.slice(1).map(b => ({
            test: b.conditionExpr,
            node: this.lowerSvelteTemplateTree(b.node),
          })),
          elseNode: decisionTree.fallbackNode ? this.lowerSvelteTemplateTree(decisionTree.fallbackNode) : undefined,
        };
      }
    }

    // Lower Svelte {#each items as item, i (item.id)}
    if (res.loop) {
      res.loop.bodyNode = this.lowerSvelteTemplateTree(res.loop.bodyNode);
    }

    if (res.children && res.children.length > 0) {
      res.children = res.children.map(c => this.lowerSvelteTemplateTree(c));
    }

    return res;
  }
}
