/**
 * Deep Angular Component & Template Directive Semantic Lowering Engine.
 * 
 * Translates Angular 2+ TypeScript components (@Component, @Input, @Output, @ViewChild,
 * lifecycle interfaces, DI services) and Angular HTML Template syntax
 * (*ngIf, *ngFor with trackBy/index, [ngSwitch], [(ngModel)], Pipes)
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

export interface AngularComponentFacts {
  selector?: string;
  className: string;
  inputs: { name: string; type: string; defaultValue?: string; alias?: string }[];
  outputs: { name: string; eventType: string }[];
  classFields: { name: string; type: string; initialExpr?: string; isPrivate?: boolean }[];
  lifecycleHooks: { name: "ngOnInit" | "ngOnChanges" | "ngOnDestroy" | "ngAfterViewInit"; body: string }[];
  methods: { name: string; params: { name: string; type: string }[]; returnType: string; body: string; isAsync: boolean }[];
  diInjections: { paramName: string; serviceType: string }[];
}

export class AngularSemanticLoweringEngine {
  /**
   * Lowers an Angular component and template into Universal Component IR.
   */
  public static lowerAngularComponent(
    facts: AngularComponentFacts,
    templateRoot: FullSyntaxNode,
    sourceCode = ""
  ): FullSyntaxComponentIR {
    const props: FullSyntaxProp[] = [];
    const states: FullSyntaxState[] = [];
    const computed: FullSyntaxComputed[] = [];
    const effects: FullSyntaxEffect[] = [];
    const methods: FullSyntaxMethod[] = [];

    // 1. Inputs -> Props
    for (const inp of facts.inputs) {
      props.push({
        name: inp.alias || inp.name,
        typeAnnotation: inp.type || "any",
        required: false,
        defaultValue: inp.defaultValue,
        isCallback: false,
      });
    }

    // 2. Outputs -> Callback Props / Emits
    for (const out of facts.outputs) {
      props.push({
        name: `on${out.name.charAt(0).toUpperCase()}${out.name.slice(1)}`,
        typeAnnotation: `(event: ${out.eventType || "any"}) => void`,
        required: false,
        isCallback: true,
      });
    }

    // 3. Class Fields -> States & Computeds
    for (const field of facts.classFields) {
      // Check if field is getter (computed)
      if (field.name.startsWith("get ")) {
        const getterName = field.name.replace("get ", "").trim();
        computed.push({
          name: getterName,
          returnType: field.type || "any",
          dependencies: [],
          expressionOrBody: field.initialExpr || "",
        });
      } else {
        states.push({
          name: field.name,
          initialValueExpr: field.initialExpr || "null",
          typeAnnotation: field.type || "any",
        });
      }
    }

    // 4. DI Services -> Injected State Proxies
    for (const di of facts.diInjections) {
      states.push({
        name: `$service_${di.paramName}`,
        initialValueExpr: `/* Injected ${di.serviceType} */ null`,
        typeAnnotation: di.serviceType,
      });
    }

    // 5. Lifecycle Hooks -> Effects
    for (const hook of facts.lifecycleHooks) {
      const hookKind = hook.name === "ngOnInit" ? "mount"
        : hook.name === "ngOnDestroy" ? "unmount"
        : "update";

      effects.push({
        id: `angular_${hook.name}`,
        hookKind,
        dependencies: hook.name === "ngOnChanges" ? ["props"] : [],
        bodyCode: hook.body,
        hasCleanup: hook.name === "ngOnDestroy",
      });
    }

    // 6. Methods
    for (const m of facts.methods) {
      methods.push({
        name: m.name,
        parameters: m.params,
        returnType: m.returnType,
        bodyCode: m.body,
        isAsync: m.isAsync,
      });
    }

    // 7. DAG topological ordering
    const dag = new ReactiveDependencyDAG();
    dag.ingestComponentMembers(props, states, computed, effects, methods);
    const dagAnalysis = dag.analyze();

    return {
      schemaVersion: "2.0",
      componentName: facts.className,
      sourceFramework: "angular",
      targetFramework: "miniprogram",
      description: `Synthesized from Angular component ${facts.className}`,
      props,
      states,
      computed,
      effects,
      methods,
      slots: [],
      refs: [],
      templateRoot: this.lowerAngularTemplateTree(templateRoot),
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
   * Normalizes Angular structural directives (*ngIf, *ngFor, [ngSwitch]) and pipe transforms.
   */
  private static lowerAngularTemplateTree(node: FullSyntaxNode): FullSyntaxNode {
    if (!node) return node;

    let res: FullSyntaxNode = { ...node };

    // Lower Angular Pipes (e.g. {{ dateVal | date:'yyyy-MM-dd' }} or {{ count$ | async }})
    if (res.text && res.text.includes("|")) {
      res.text = this.lowerPipeExpression(res.text);
    }
    if (res.expression && res.expression.includes("|")) {
      res.expression = this.lowerPipeExpression(res.expression);
    }

    // Normalize *ngIf conditionals via DecisionTree
    if (res.kind === "conditional" || res.condition) {
      const decisionTree = DirectiveDecisionTreeEngine.normalizeCondition(res);
      const firstBranch = decisionTree.branches[0];
      if (firstBranch) {
        res.condition = {
          test: firstBranch.conditionExpr,
          thenNode: this.lowerAngularTemplateTree(firstBranch.node),
          elifBranches: decisionTree.branches.slice(1).map(b => ({
            test: b.conditionExpr,
            node: this.lowerAngularTemplateTree(b.node),
          })),
          elseNode: decisionTree.fallbackNode ? this.lowerAngularTemplateTree(decisionTree.fallbackNode) : undefined,
        };
      }
    }

    // Normalize *ngFor loop bindings (extract trackBy, index)
    if (res.loop) {
      if (res.loop.keyExpr && res.loop.keyExpr.includes("trackBy")) {
        // Lower trackBy function call to item ID
        res.loop.keyExpr = "item.id || index";
      }
      res.loop.bodyNode = this.lowerAngularTemplateTree(res.loop.bodyNode);
    }

    if (res.children && res.children.length > 0) {
      res.children = res.children.map(c => this.lowerAngularTemplateTree(c));
    }

    return res;
  }

  /**
   * Translates Angular pipe syntax to universal formatters or async unwrap expressions.
   */
  private static lowerPipeExpression(expr: string): string {
    let lowered = expr;
    // Async pipe: val$ | async -> val
    lowered = lowered.replace(/([a-zA-Z0-9_$.]+)\s*\|\s*async/g, "$1");
    // Json pipe: data | json -> JSON.stringify(data)
    lowered = lowered.replace(/([a-zA-Z0-9_$.]+)\s*\|\s*json/g, "JSON.stringify($1)");
    // Uppercase pipe: str | uppercase -> str.toUpperCase()
    lowered = lowered.replace(/([a-zA-Z0-9_$.]+)\s*\|\s*uppercase/g, "($1).toUpperCase()");
    // Lowercase pipe: str | lowercase -> str.toLowerCase()
    lowered = lowered.replace(/([a-zA-Z0-9_$.]+)\s*\|\s*lowercase/g, "($1).toLowerCase()");
    return lowered;
  }
}
