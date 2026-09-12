/**
 * WeChat MiniApp Native Component & Page Reverse Lowering Engine.
 * 
 * Reverses native MiniApp 4-file artifacts (.wxml, .js/.ts, .json, .wxss)
 * back into canonical FullSyntaxComponentIR for bidirectional transpilation to Vue 3 and React.
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

export interface MiniAppSpecFacts {
  componentName: string;
  isPage: boolean;
  properties: Record<string, { type: string; value?: any; observer?: string }>;
  data: Record<string, any>;
  observers: Record<string, string>; // 'fieldA, fieldB': 'fnName'
  lifetimes: Record<string, string>; // 'attached', 'ready', 'detached'
  pageLifetimes: Record<string, string>; // 'show', 'hide'
  methods: Record<string, { params: string[]; body: string; isAsync: boolean }>;
  wxmlTemplateRoot: FullSyntaxNode;
}

export class MiniAppReverseLoweringEngine {
  /**
   * Reverses native MiniApp facts and template to Universal Component IR.
   */
  public static reverseToUniversalIR(
    facts: MiniAppSpecFacts,
    rawJsCode = ""
  ): FullSyntaxComponentIR {
    const props: FullSyntaxProp[] = [];
    const states: FullSyntaxState[] = [];
    const computed: FullSyntaxComputed[] = [];
    const effects: FullSyntaxEffect[] = [];
    const methods: FullSyntaxMethod[] = [];

    // 1. Properties -> Props
    for (const [propName, propDef] of Object.entries(facts.properties)) {
      props.push({
        name: propName,
        typeAnnotation: this.mapMiniAppTypeToTs(propDef.type),
        required: propDef.value === undefined,
        defaultValue: propDef.value !== undefined ? JSON.stringify(propDef.value) : undefined,
        isCallback: propName.startsWith("bind") || propName.startsWith("catch"),
      });

      // If observer is specified, register as an Effect watcher
      if (propDef.observer) {
        effects.push({
          id: `observer_${propName}`,
          hookKind: "watch",
          dependencies: [propName],
          bodyCode: `this.${propDef.observer}(newVal, oldVal);`,
          hasCleanup: false,
        });
      }
    }

    // 2. Data -> States
    for (const [key, val] of Object.entries(facts.data)) {
      states.push({
        name: key,
        initialValueExpr: typeof val === "object" ? JSON.stringify(val) : String(val),
        typeAnnotation: typeof val,
      });
    }

    // 3. Observers -> Effects
    for (const [fields, handlerCode] of Object.entries(facts.observers)) {
      const deps = fields.split(",").map(f => f.trim()).filter(Boolean);
      effects.push({
        id: `observer_${deps.join("_")}`,
        hookKind: "watch",
        dependencies: deps,
        bodyCode: handlerCode,
        hasCleanup: false,
      });
    }

    // 4. Lifetimes -> Effects
    for (const [lifetime, body] of Object.entries(facts.lifetimes)) {
      const hookKind = (lifetime === "attached" || lifetime === "onLoad" || lifetime === "onReady")
        ? "mount"
        : (lifetime === "detached" || lifetime === "onUnload")
        ? "unmount"
        : "update";

      effects.push({
        id: `miniapp_${lifetime}`,
        hookKind,
        dependencies: [],
        bodyCode: body,
        hasCleanup: hookKind === "unmount",
      });
    }

    // 5. Methods
    for (const [methodName, methodDef] of Object.entries(facts.methods)) {
      methods.push({
        name: methodName,
        parameters: methodDef.params.map(p => ({ name: p, type: "any" })),
        returnType: "any",
        bodyCode: methodDef.body,
        isAsync: methodDef.isAsync,
      });
    }

    // 6. DAG Reordering
    const dag = new ReactiveDependencyDAG();
    dag.ingestComponentMembers(props, states, computed, effects, methods);
    const dagAnalysis = dag.analyze();

    return {
      schemaVersion: "2.0",
      componentName: facts.componentName,
      sourceFramework: "miniprogram",
      targetFramework: "vue3",
      description: `Reversed from native WeChat MiniApp ${facts.isPage ? "Page" : "Component"} ${facts.componentName}`,
      props,
      states,
      computed,
      effects,
      methods,
      slots: [],
      refs: [],
      templateRoot: facts.wxmlTemplateRoot,
      styles: { scopedCss: "" },
      containerApis: [],
      thirdPartyComponents: [],
      rawSourceLinesCount: rawJsCode.split("\n").length,
      metadata: {
        dagAnalysis: {
          cycleDetected: dagAnalysis.cycles.length > 0,
          topologicalOrder: dagAnalysis.topologicalOrder,
        },
      },
    };
  }

  private static mapMiniAppTypeToTs(miniappType: string): string {
    const t = (miniappType || "").toLowerCase();
    if (t.includes("string")) return "string";
    if (t.includes("number")) return "number";
    if (t.includes("boolean")) return "boolean";
    if (t.includes("array")) return "any[]";
    if (t.includes("object")) return "Record<string, any>";
    return "any";
  }
}
