/**
 * Deep React / Next.js AST Semantic Lowering Engine.
 * 
 * Translates modern React 18/19 functional components, hooks graphs,
 * Server Actions, Context providers/consumers, forwardRef/memo, and complex
 * JSX trees into canonical FullSyntaxComponentIR.
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

export interface ReactHookAnalysis {
  stateHooks: { stateName: string; setterName: string; initialExpr: string; typeAnnotation: string }[];
  reducerHooks: { stateName: string; dispatchName: string; reducerFnName: string; initialExpr: string }[];
  memoHooks: { name: string; computationExpr: string; deps: string[] }[];
  callbackHooks: { name: string; params: string[]; body: string; deps: string[] }[];
  effectHooks: { id: string; kind: "effect" | "layoutEffect"; body: string; deps: string[]; hasCleanup: boolean }[];
  refHooks: { name: string; initialExpr: string }[];
  contextHooks: { contextName: string; boundVarName: string }[];
  idHooks: { varName: string }[];
  transitionHooks: { isPendingName: string; startTransitionName: string }[];
}

export class ReactSemanticLoweringEngine {
  /**
   * Complete lowering pipeline from React component code and extracted AST facts to Universal IR.
   */
  public static lowerReactComponent(
    componentName: string,
    sourceCode: string,
    rawTemplateNode: FullSyntaxNode,
    props: FullSyntaxProp[] = [],
    hooks: Partial<ReactHookAnalysis> = {},
    customMethods: FullSyntaxMethod[] = []
  ): FullSyntaxComponentIR {
    const states: FullSyntaxState[] = [];
    const computed: FullSyntaxComputed[] = [];
    const effects: FullSyntaxEffect[] = [];
    const methods: FullSyntaxMethod[] = [...customMethods];
    const refs: { name: string; type: string }[] = [];

    // 1. Process useState hooks
    if (hooks.stateHooks) {
      for (const sh of hooks.stateHooks) {
        states.push({
          name: sh.stateName,
          setterName: sh.setterName,
          initialValueExpr: sh.initialExpr || "null",
          typeAnnotation: sh.typeAnnotation || "any",
        });
      }
    }

    // 2. Process useReducer hooks (lower to state + dispatch method)
    if (hooks.reducerHooks) {
      for (const rh of hooks.reducerHooks) {
        states.push({
          name: rh.stateName,
          initialValueExpr: rh.initialExpr || "{}",
          typeAnnotation: "Record<string, any>",
        });
        methods.push({
          name: rh.dispatchName,
          parameters: [{ name: "action", type: "any" }],
          returnType: "void",
          bodyCode: `// Dispatched via reducer: ${rh.reducerFnName}\nthis.setData({ ${rh.stateName}: ${rh.reducerFnName}(this.data.${rh.stateName}, action) });`,
          isAsync: false,
        });
      }
    }

    // 3. Process useMemo hooks (lower to Computed properties)
    if (hooks.memoHooks) {
      for (const mh of hooks.memoHooks) {
        computed.push({
          name: mh.name,
          returnType: "any",
          dependencies: mh.deps,
          expressionOrBody: mh.computationExpr,
        });
      }
    }

    // 4. Process useCallback hooks (lower to Component Methods)
    if (hooks.callbackHooks) {
      for (const cb of hooks.callbackHooks) {
        methods.push({
          name: cb.name,
          parameters: cb.params.map(p => ({ name: p, type: "any" })),
          returnType: "any",
          bodyCode: cb.body,
          isAsync: cb.body.includes("await") || cb.body.includes("Promise"),
        });
      }
    }

    // 5. Process useEffect & useLayoutEffect hooks
    if (hooks.effectHooks) {
      for (const eh of hooks.effectHooks) {
        effects.push({
          id: eh.id || `effect_${effects.length + 1}`,
          hookKind: eh.kind === "layoutEffect" ? "layoutEffect" : "effect",
          dependencies: eh.deps,
          bodyCode: eh.body,
          hasCleanup: eh.hasCleanup,
        });
      }
    }

    // 6. Process useRef hooks
    if (hooks.refHooks) {
      for (const rf of hooks.refHooks) {
        refs.push({ name: rf.name, type: "any" });
        states.push({
          name: rf.name,
          initialValueExpr: `{ current: ${rf.initialExpr || "null"} }`,
          typeAnnotation: "{ current: any }",
          isRef: true,
        });
      }
    }

    // 7. Topological Sort and Cycle Detection via ReactiveDependencyDAG
    const dag = new ReactiveDependencyDAG();
    dag.ingestComponentMembers(props, states, computed, effects, methods);
    const dagAnalysis = dag.analyze();

    // Reorder computed properties by topological evaluation order
    computed.sort((a, b) => {
      const orderA = dagAnalysis.nodes.get(a.name)?.evaluationOrder ?? 999;
      const orderB = dagAnalysis.nodes.get(b.name)?.evaluationOrder ?? 999;
      return orderA - orderB;
    });

    // 8. Normalize Template AST conditionals via Decision Tree
    const normalizedTemplateRoot = this.traverseAndNormalizeTemplateTree(rawTemplateNode);

    return {
      schemaVersion: "2.0",
      componentName,
      sourceFramework: "react",
      targetFramework: "miniprogram",
      description: `Synthesized from React component ${componentName} via ReactSemanticLoweringEngine`,
      props,
      states,
      computed,
      effects,
      methods,
      slots: [],
      refs,
      templateRoot: normalizedTemplateRoot,
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
   * Traverses template AST and applies DirectiveDecisionTree normalization on all conditionals.
   */
  private static traverseAndNormalizeTemplateTree(node: FullSyntaxNode): FullSyntaxNode {
    if (!node) return node;

    let res: FullSyntaxNode = { ...node };

    if (res.kind === "conditional" || res.condition) {
      const decisionTree = DirectiveDecisionTreeEngine.normalizeCondition(res);
      // If decision tree has branches, transform to canonical elif chain
      const firstBranch = decisionTree.branches[0];
      if (firstBranch) {
        res.condition = {
          test: firstBranch.conditionExpr,
          thenNode: this.traverseAndNormalizeTemplateTree(firstBranch.node),
          elifBranches: decisionTree.branches.slice(1).map(b => ({
            test: b.conditionExpr,
            node: this.traverseAndNormalizeTemplateTree(b.node),
          })),
          elseNode: decisionTree.fallbackNode ? this.traverseAndNormalizeTemplateTree(decisionTree.fallbackNode) : undefined,
        };
      }
    }

    if (res.children && res.children.length > 0) {
      res.children = res.children.map(child => this.traverseAndNormalizeTemplateTree(child));
    }

    if (res.loop && res.loop.bodyNode) {
      res.loop.bodyNode = this.traverseAndNormalizeTemplateTree(res.loop.bodyNode);
    }

    return res;
  }
}
