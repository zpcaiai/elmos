import { FullSyntaxComponentIR, FullSyntaxNode, TargetFramework } from "../types";

export class UiLibraryTransformer {
  private static readonly MINIAPP_TAG_MAP: Record<string, string> = {
    // HTML Containers -> view
    div: "view",
    section: "view",
    article: "view",
    header: "view",
    footer: "view",
    nav: "view",
    aside: "view",
    main: "view",
    ul: "view",
    ol: "view",
    li: "view",
    dl: "view",
    dt: "view",
    dd: "view",
    details: "view",
    summary: "view",
    table: "view",
    thead: "view",
    tbody: "view",
    tfoot: "view",
    tr: "view",
    th: "view",
    td: "view",

    // HTML Inline -> text
    span: "text",
    p: "view",
    strong: "text",
    em: "text",
    b: "text",
    i: "text",
    small: "text",
    code: "text",
    label: "text",

    // Headings -> view
    h1: "view",
    h2: "view",
    h3: "view",
    h4: "view",
    h5: "view",
    h6: "view",

    // Navigation & media
    a: "navigator",
    img: "image",

    // Third-party UI components
    Button: "button",
    Input: "input",
    Textarea: "textarea",
    Card: "view",
    Modal: "view",
    Table: "view",
    Icon: "text",
    Row: "view",
    Col: "view",
    Divider: "view",
    Badge: "view",
    Tag: "view",
    Tabs: "view",
    Tab: "view",
    Switch: "switch",
    Checkbox: "checkbox",
    Radio: "radio",
    Avatar: "image",
    Tooltip: "view",
    Popover: "view",
  };

  public transform(ir: FullSyntaxComponentIR, target: TargetFramework): void {
    if (target === "miniapp") {
      this.lowerNodeTags(ir.templateRoot);
    }
  }

  private lowerNodeTags(node: FullSyntaxNode): void {
    if (!node) return;

    if (node.tag) {
      const origTag = node.tag;
      const mapped = UiLibraryTransformer.MINIAPP_TAG_MAP[origTag] || (node.kind === "element" ? "view" : undefined);
      if (mapped) {
        node.tag = mapped;
        // If it was a table tag or semantic container, preserve the semantic class
        if (["table", "thead", "tbody", "tr", "th", "td", "strong", "em", "code", "small"].includes(origTag)) {
          node.attrs = node.attrs || [];
          const classAttr = node.attrs.find((a) => a.name === "class");
          if (classAttr) {
            if (!classAttr.value.includes(origTag)) {
              classAttr.value = `${origTag} ${classAttr.value}`;
            }
          } else {
            node.attrs.push({ name: "class", value: origTag, isDynamic: false });
          }
        }
      }
    }

    if (node.children) {
      for (const child of node.children) {
        this.lowerNodeTags(child);
      }
    }

    if (node.condition) {
      this.lowerNodeTags(node.condition.thenNode);
      if (node.condition.elseNode) {
        this.lowerNodeTags(node.condition.elseNode);
      }
    }

    if (node.loop) {
      this.lowerNodeTags(node.loop.bodyNode);
    }
  }
}
