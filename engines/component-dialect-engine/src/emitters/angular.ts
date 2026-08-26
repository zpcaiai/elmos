/**
 * Emits certified-component-v1 canonical model as a standalone Angular
 * component with an inline template.
 *
 * Angular's binding syntax is its own and is not interchangeable with
 * Vue's despite looking superficially similar:
 *  - Property binding is `[attr]="expr"`, event binding is
 *    `(click)="stmt"`; `:attr`/`@click` are Vue and mean nothing here.
 *  - Conditionals are `*ngIf` with an `else` template reference, not a
 *    sibling `v-else`.
 *  - Props are `@Input()` fields; outputs are `@Output()` EventEmitters,
 *    so a callback prop becomes `done.emit(value)`.
 *  - Class fields are read bare in the template but need `this.` in the
 *    class body.
 */
import { AttrBinding, ComponentDef, EventName, Expr, ListPropDef, Literal, Node as CNode, PropDef, Stmt } from "../models";
import { dataPropTypeSource, listElementTypeSource, listPropIndex, referencedComponents } from "./react";

const ANGULAR_EVENT: Record<EventName, string> = {
  onClick: "click", onChange: "change", onInput: "input", onSubmit: "submit",
};

/** Angular binds to DOM *properties*, so a few HTML attribute names differ. */
const PROPERTY_NAME: Record<string, string> = { class: "class", for: "htmlFor" };

function tsType(t: "string" | "number" | "boolean"): string { return t; }

function literalSource(literal: Literal): string {
  if (literal.type === "string") return JSON.stringify(literal.value);
  if (literal.type === "number") return String(literal.value);
  if (literal.type === "null") return "null";
  return literal.value ? "true" : "false";
}

function exprSource(expr: Expr, inClass: boolean): string {
  const wrap = (e: Expr): string => {
    const src = exprSource(e, inClass);
    return e.kind === "binary" || e.kind === "ternary" ? `(${src})` : src;
  };
  switch (expr.kind) {
    case "ident": return inClass ? `this.${expr.name}` : expr.name;
    // `*ngFor` binds the loop variable as a template-local; `this.` is wrong.
    case "member": return `${expr.object}.${expr.field}`;
    case "path": return `${expr.object}.${expr.fields.join(".")}`;
    case "literal": return literalSource(expr.literal);
    case "unaryNot": return `!${wrap(expr.operand)}`;
    case "binary": {
      const op = expr.operator === "==" ? "===" : expr.operator === "!=" ? "!==" : expr.operator;
      return `${wrap(expr.left)} ${op} ${wrap(expr.right)}`;
    }
    case "stringMethod": return `${wrap(expr.receiver)}.${expr.method}(${expr.args.map((arg) => exprSource(arg, inClass)).join(", ")})`;
    case "arrayLength": return `${wrap(expr.operand)}.length`;
    case "ternary": return `${wrap(expr.condition)} ? ${wrap(expr.then)} : ${wrap(expr.else)}`;
  }
}

export function outputNameForCallback(callbackName: string): string {
  const rest = callbackName.slice(2);
  return rest.charAt(0).toLowerCase() + rest.slice(1);
}

function stmtSource(stmt: Stmt): string {
  // Rendered inside a template `(click)="..."` binding, where names are bare.
  if (stmt.kind === "setState") return `${stmt.target} = ${exprSource(stmt.value, false)}`;
  const args = stmt.args.map((a) => exprSource(a, false)).join(", ");
  return `${outputNameForCallback(stmt.target)}.emit(${args})`;
}

function handlerSource(body: Stmt[]): string {
  return body.map(stmtSource).join("; ").replace(/"/g, "&quot;");
}

function attrSource(attr: AttrBinding): string {
  const name = PROPERTY_NAME[attr.name] ?? attr.name;
  if (attr.kind === "static") return `${attr.name}=${JSON.stringify(attr.value)}`;
  return `[${name}]="${exprSource(attr.value, false).replace(/"/g, "&quot;")}"`;
}

interface TemplateContext {
  /** Named <ng-template> blocks generated for *ngIf else branches. */
  elseTemplates: string[];
  counter: { n: number };
  lists: ReadonlyMap<string, ListPropDef>;
}

function nodeSource(node: CNode, indent: string, ctx: TemplateContext): string {
  if (node.kind === "text") {
    if (node.value.kind === "literal" && node.value.literal.type === "string") return `${indent}${node.value.literal.value}`;
    return `${indent}{{ ${exprSource(node.value, false)} }}`;
  }
  if (node.kind === "conditional") {
    const cond = exprSource(node.condition, false).replace(/"/g, "&quot;");
    if (node.else === null) return withDirective(node.then, `*ngIf="${cond}"`, indent, ctx);
    // Angular has no sibling `v-else`; the else branch must be a named
    // <ng-template> referenced from the *ngIf.
    const ref = `elseBlock${ctx.counter.n++}`;
    const elseBody = nodeSource(node.else, "      ", ctx);
    ctx.elseTemplates.push(`    <ng-template #${ref}>\n${elseBody}\n    </ng-template>`);
    return withDirective(node.then, `*ngIf="${cond}; else ${ref}"`, indent, ctx);
  }
  if (node.kind === "component") {
    // Angular addresses a child by its SELECTOR, not its class name, and
    // binds inputs with [name]. Emitting <Child> here would silently
    // render nothing -- Angular ignores unknown elements in a template
    // whose component was never imported.
    const args = node.props.map((a) => `[${a.name}]="${exprSource(a.value, false).replace(/"/g, "&quot;")}"`);
    return `${indent}<app-${kebab(node.name)}${args.length ? " " + args.join(" ") : ""}></app-${kebab(node.name)}>`;
  }
  if (node.kind === "list") {
    // Angular's identity hook is `trackBy`, which requires a component
    // method -- outside this profile's "no methods" rule. Plain *ngFor is
    // correct without it; it just re-creates DOM nodes on reorder.
    const source = node.sourceExpression === undefined ? node.source : exprSource(node.sourceExpression, false);
    return withDirective(node.body, `*ngFor="let ${node.itemName} of ${source}"`, indent, ctx);
  }
  return elementSource(node, [], indent, ctx);
}

function withDirective(node: CNode, directive: string, indent: string, ctx: TemplateContext): string {
  if (node.kind === "element") return elementSource(node, [directive], indent, ctx);
  const inner = nodeSource(node, indent + "  ", ctx);
  return `${indent}<ng-container ${directive}>\n${inner}\n${indent}</ng-container>`;
}

function elementSource(node: Extract<CNode, { kind: "element" }>, extraDirectives: string[], indent: string, ctx: TemplateContext): string {
  const parts = [
    ...extraDirectives,
    ...node.attrs.map(attrSource),
    ...node.events.map((e) => `(${ANGULAR_EVENT[e.name]})="${handlerSource(e.body)}"`),
  ];
  const attrText = parts.length > 0 ? " " + parts.join(" ") : "";
  if (node.children.length === 0) return `${indent}<${node.tag}${attrText}></${node.tag}>`;
  if (node.children.every((c) => c.kind === "text")) {
    const inline = node.children.map((c) => nodeSource(c, "", ctx).trim()).join("");
    return `${indent}<${node.tag}${attrText}>${inline}</${node.tag}>`;
  }
  const childSrc = node.children.map((c) => nodeSource(c, indent + "  ", ctx)).join("\n");
  return `${indent}<${node.tag}${attrText}>\n${childSrc}\n${indent}</${node.tag}>`;
}

function kebab(name: string): string {
  return name.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
}

export function emitAngular(component: ComponentDef): string {
  const ctx: TemplateContext = { elseTemplates: [], counter: { n: 0 }, lists: listPropIndex(component) };
  const templateBody = nodeSource(component.root, "    ", ctx);
  const template = [templateBody, ...ctx.elseTemplates].join("\n");

  const dataProps = component.props.filter((p): p is Extract<PropDef, { kind: "data" }> => p.kind === "data");
  const callbacks = component.props.filter((p): p is Extract<PropDef, { kind: "callback" }> => p.kind === "callback");

  const imports = ["Component"];
  if (dataProps.length > 0) imports.push("Input");
  if (callbacks.length > 0) imports.push("Output", "EventEmitter");

  const lines: string[] = [];
  lines.push(`import { ${imports.join(", ")} } from "@angular/core";`);
  lines.push(`import { CommonModule } from "@angular/common";`);
  // A standalone Angular component must BOTH import the class and list it
  // in `imports`. Missing the second silently renders nothing -- Angular
  // treats the unknown selector as an inert element.
  const children = referencedComponents(component);
  for (const child of children) {
    lines.push(`import { ${child}Component } from "./${kebab(child)}.component";`);
  }
  lines.push("");
  lines.push(`@Component({`);
  lines.push(`  selector: "app-${kebab(component.name)}",`);
  lines.push(`  standalone: true,`);
  lines.push(`  imports: [CommonModule${children.map((c) => `, ${c}Component`).join("")}],`);
  lines.push(`  template: \``);
  lines.push(template);
  lines.push(`  \`,`);
  lines.push(`})`);
  lines.push(`export class ${component.name}Component {`);

  for (const prop of dataProps) {
    if (prop.defaultValue !== undefined) {
      lines.push(`  @Input() ${prop.name}: ${dataPropTypeSource(prop, "unknown")} = ${literalSource(prop.defaultValue)};`);
    } else if (prop.required) {
      // Definite-assignment assertion: Angular assigns @Input before the
      // first change detection pass, which `strictPropertyInitialization`
      // cannot see.
      lines.push(`  @Input() ${prop.name}!: ${dataPropTypeSource(prop, "unknown")};`);
    } else {
      lines.push(`  @Input() ${prop.name}?: ${dataPropTypeSource(prop, "unknown")};`);
    }
  }
  for (const list of component.props.filter((p): p is ListPropDef => p.kind === "list")) {
    lines.push(`  @Input() ${list.name}: ${listElementTypeSource(list)}[] = [];`);
  }
  for (const cb of callbacks) {
    const payload = cb.paramType ? tsType(cb.paramType) : "void";
    lines.push(`  @Output() ${outputNameForCallback(cb.name)} = new EventEmitter<${payload}>();`);
  }
  for (const s of component.state) {
    lines.push(`  ${s.name}: ${tsType(s.stateType)}${s.nullable ? " | null" : ""} = ${literalSource(s.initial)};`);
  }
  lines.push(`}`);
  return lines.join("\n") + "\n";
}
