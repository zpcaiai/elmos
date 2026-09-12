import {
  FullSyntaxComponentIR,
  FullSyntaxNode,
  FullSyntaxProp,
  FullSyntaxState,
} from "../types";
import {
  ArkUIComponentAst,
  ArkUIModifier,
  ArkUINode,
  ArkUIStateProperty,
} from "./arkui-full-ast-types";

export interface ArkUILoweringOptions {
  enableLazyForEach?: boolean;
  viewportUnit?: "vp" | "px";
  enableGestureRecognition?: boolean;
}

export class ArkUISemanticLowering {
  private options: Required<ArkUILoweringOptions>;
  private nodeCounter = 0;

  constructor(options: ArkUILoweringOptions = {}) {
    this.options = {
      enableLazyForEach: options.enableLazyForEach ?? true,
      viewportUnit: options.viewportUnit ?? "vp",
      enableGestureRecognition: options.enableGestureRecognition ?? true,
    };
  }

  private nextId(prefix = "ark_lower"): string {
    return `${prefix}_${this.nodeCounter++}`;
  }

  public lowerToArkUI(ir: FullSyntaxComponentIR): ArkUIComponentAst {
    const stateProperties: ArkUIStateProperty[] = [];
    const builderParams = ir.slots.map((s) => ({
      name: s.name === "default" ? "defaultSlot" : s.name,
      typeAnnotation: "() => void",
      required: false,
    }));

    // Lower State
    for (const st of ir.states) {
      stateProperties.push({
        name: st.name,
        decorator: { kind: "@State" },
        typeAnnotation: st.typeAnnotation || "any",
        initialValueExpr: st.initialValueExpr,
      });
    }

    // Lower Props
    for (const pr of ir.props) {
      const isTwoWay = pr.name.startsWith("model") || pr.name.endsWith("Change");
      stateProperties.push({
        name: pr.name,
        decorator: { kind: isTwoWay ? "@Link" : "@Prop" },
        typeAnnotation: pr.typeAnnotation || "any",
        initialValueExpr: pr.defaultValue !== undefined ? JSON.stringify(pr.defaultValue) : undefined,
      });
    }

    // Lower Template Root
    const buildRoot = ir.templateRoot
      ? this.lowerNode(ir.templateRoot)
      : {
          id: this.nextId("root"),
          kind: "container" as const,
          componentName: "Column",
          modifiers: [{ name: "width", args: ["'100%'"] }],
          children: [],
        };

    // Lower Lifecycle
    const lifecycleMethods: ArkUIComponentAst["lifecycleMethods"] = [];
    for (const ef of ir.effects) {
      if (ef.hookKind === "mount") {
        lifecycleMethods.push({
          name: "aboutToAppear",
          bodyCode: ef.bodyCode,
        });
      } else if (ef.hookKind === "unmount") {
        lifecycleMethods.push({
          name: "aboutToDisappear",
          bodyCode: ef.bodyCode,
        });
      }
    }

    // Lower Methods
    const customMethods = ir.methods.map((m) => ({
      name: m.name,
      parameters: m.parameters,
      returnType: m.returnType,
      bodyCode: m.bodyCode,
      isAsync: m.isAsync,
    }));

    return {
      structName: ir.componentName,
      isEntry: !!ir.metadata?.isEntry,
      isPreview: !!ir.metadata?.isPreview,
      stateProperties,
      builderParams,
      builderMethods: [],
      stylesMethods: [],
      extendMethods: [],
      lifecycleMethods,
      customMethods,
      buildRoot,
      importedModules: [],
    };
  }

  public liftToUniversal(ast: ArkUIComponentAst): FullSyntaxComponentIR {
    const states: FullSyntaxState[] = [];
    const props: FullSyntaxProp[] = [];

    for (const p of ast.stateProperties) {
      if (p.decorator.kind === '@Prop' || p.decorator.kind === '@Link') {
        props.push({
          name: p.name,
          typeAnnotation: p.typeAnnotation,
          required: p.decorator.kind === '@Link',
          defaultValue: p.initialValueExpr,
          isCallback: false,
        });
      } else {
        states.push({
          name: p.name,
          initialValueExpr: p.initialValueExpr || 'undefined',
          typeAnnotation: p.typeAnnotation,
        });
      }
    }

    return {
      schemaVersion: '2.0',
      componentName: ast.structName || 'ArkComponent',
      sourceFramework: 'arkui',
      props,
      states,
      computed: [],
      effects: ast.lifecycleMethods.map((l) => ({
        id: `effect_${l.name}`,
        hookKind: l.name === 'aboutToAppear' ? 'mount' : l.name === 'aboutToDisappear' ? 'unmount' : 'update',
        dependencies: [],
        bodyCode: l.bodyCode,
        hasCleanup: false,
      })),
      methods: ast.customMethods.map((m) => ({
        name: m.name,
        parameters: m.parameters,
        returnType: m.returnType,
        bodyCode: m.bodyCode,
        isAsync: m.isAsync,
      })),
      slots: ast.builderParams.map((b) => ({
        name: b.name === 'defaultSlot' ? 'default' : b.name,
        slotProps: [],
        fallbackNodes: [],
      })),
      refs: [],
      templateRoot: this.liftNode(ast.buildRoot),
      styles: {},
      containerApis: [],
      thirdPartyComponents: [],
      rawSourceLinesCount: 0,
      metadata: {},
    };
  }

  private liftNode(node: ArkUINode): FullSyntaxNode {
    let tag = 'view';
    if (node.componentName === 'Text') tag = 'text';
    else if (node.componentName === 'Button') tag = 'button';
    else if (node.componentName === 'Image') tag = 'image';

    const attrs = [];
    const events = [];

    for (const mod of node.modifiers) {
      if (mod.isEvent) {
        events.push({
          name: mod.name.replace(/^on/, '').toLowerCase(),
          handlerNameOrExpr: mod.args[0] || '',
        });
      } else {
        attrs.push({
          name: mod.name,
          value: mod.args.join(', '),
          isDynamic: false,
        });
      }
    }

    return {
      id: node.id,
      kind: 'element',
      tag,
      attrs,
      events,
      text: node.componentName === 'Text' && node.constructorArgs && node.constructorArgs[0] ? node.constructorArgs[0].replace(/^'|'$/g, '') : undefined,
      children: (node.children || []).map((c) => this.liftNode(c)),
    };
  }

  private lowerNode(node: FullSyntaxNode): ArkUINode {
    const modifiers: ArkUIModifier[] = [];

    // Map attributes to modifiers
    if (node.attrs) {
      for (const attr of node.attrs) {
        if (attr.name === "style") {
          this.extractStyleModifiers(attr.value, modifiers);
        } else if (attr.name === "class" || attr.name === "className") {
          modifiers.push({ name: "id", args: [`'${attr.value}'`] });
        } else if (attr.name === "width") {
          modifiers.push({ name: "width", args: [this.convertUnit(attr.value)] });
        } else if (attr.name === "height") {
          modifiers.push({ name: "height", args: [this.convertUnit(attr.value)] });
        } else if (attr.name === "disabled") {
          modifiers.push({ name: "enabled", args: [attr.value === "true" ? "false" : "true"] });
        }
      }
    }

    // Map events
    if (node.events) {
      for (const ev of node.events) {
        const arg = ev.handlerNameOrExpr.includes("(")
          ? `() => { ${ev.handlerNameOrExpr} }`
          : `() => { this.${ev.handlerNameOrExpr}() }`;
        if (ev.name === "click" || ev.name === "tap") {
          modifiers.push({ name: "onClick", args: [arg], isEvent: true });
        } else if (ev.name === "change") {
          modifiers.push({ name: "onChange", args: [arg], isEvent: true });
        } else {
          modifiers.push({ name: `on${ev.name.charAt(0).toUpperCase() + ev.name.slice(1)}`, args: [arg], isEvent: true });
        }
      }
    }

    // Determine ArkUI Component Name
    let componentName = "Column";
    let kind: ArkUINode["kind"] = "container";

    if (node.tag) {
      const lower = node.tag.toLowerCase();
      if (lower === "text" || lower === "span" || lower === "p" || lower === "h1" || lower === "h2") {
        componentName = "Text";
        kind = "atomic";
      } else if (lower === "button") {
        componentName = "Button";
        kind = "atomic";
      } else if (lower === "input") {
        componentName = "TextInput";
        kind = "atomic";
      } else if (lower === "image" || lower === "img") {
        componentName = "Image";
        kind = "atomic";
      } else if (lower === "row" || lower === "header" || lower === "nav") {
        componentName = "Row";
        kind = "container";
      } else if (lower === "list" || lower === "ul" || lower === "ol") {
        componentName = "List";
        kind = "container";
      } else if (lower === "listitem" || lower === "li") {
        componentName = "ListItem";
        kind = "container";
      } else if (lower === "stack") {
        componentName = "Stack";
        kind = "container";
      } else if (/^[A-Z]/.test(node.tag)) {
        componentName = node.tag;
        kind = "custom_component";
      }
    }

    // Constructor args for Text or Button
    const constructorArgs: string[] = [];
    if (componentName === "Text") {
      if (node.text) {
        constructorArgs.push(`'${node.text.replace(/'/g, "\\'")}'`);
      } else if (node.expression) {
        constructorArgs.push(node.expression);
      }
    } else if (componentName === "Button" && node.text) {
      constructorArgs.push(`'${node.text.replace(/'/g, "\\'")}'`);
    }

    // Lower children
    const children: ArkUINode[] = (node.children || []).map((c) => this.lowerNode(c));

    // Handle loop
    let forEach: ArkUINode["forEach"] | undefined;
    if (node.loop) {
      forEach = {
        isLazy: this.options.enableLazyForEach,
        arrayExpr: node.loop.sourceExpr,
        itemParam: node.loop.itemName,
        indexParam: node.loop.indexName,
        keyGeneratorExpr: node.loop.keyExpr,
        template: [this.lowerNode(node.loop.bodyNode)],
      };
    }

    return {
      id: node.id || this.nextId("node"),
      kind,
      componentName,
      constructorArgs,
      modifiers,
      children,
      forEach,
    };
  }

  private extractStyleModifiers(styleStr: string, modifiers: ArkUIModifier[]): void {
    const pairs = styleStr.split(";").map((p) => p.trim()).filter(Boolean);
    for (const pair of pairs) {
      const [key, val] = pair.split(":").map((s) => s.trim());
      if (!key || !val) continue;

      if (key === "background-color" || key === "backgroundColor") {
        modifiers.push({ name: "backgroundColor", args: [`'${val}'`] });
      } else if (key === "font-size" || key === "fontSize") {
        modifiers.push({ name: "fontSize", args: [this.convertUnit(val)] });
      } else if (key === "color") {
        modifiers.push({ name: "fontColor", args: [`'${val}'`] });
      } else if (key === "padding") {
        modifiers.push({ name: "padding", args: [this.convertUnit(val)] });
      } else if (key === "margin") {
        modifiers.push({ name: "margin", args: [this.convertUnit(val)] });
      } else if (key === "border-radius" || key === "borderRadius") {
        modifiers.push({ name: "borderRadius", args: [this.convertUnit(val)] });
      } else if (key === "opacity") {
        modifiers.push({ name: "opacity", args: [val] });
      } else if (key === "display" && val === "flex") {
        // Will be converted to Row or Column container
      }
    }
  }

  private convertUnit(val: string): string {
    if (/^\d+$/.test(val)) return val;
    if (val.endsWith("px")) {
      const num = parseInt(val, 10);
      return isNaN(num) ? `'${val}'` : `${num}`;
    }
    if (val.endsWith("rpx") || val.endsWith("rem")) {
      const num = parseFloat(val);
      return isNaN(num) ? `'${val}'` : `${Math.round(num * 2)}`;
    }
    return `'${val}'`;
  }
}
