/**
 * Complete AST type definitions for Svelte 5 with Runes and Snippets.
 * 
 * Accurately models modern Svelte 5 components:
 * - Runes: $state, $state.raw, $derived, $derived.by, $effect, $effect.pre, $effect.root, $props, $bindable, $inspect
 * - Snippets: {#snippet name(params)} ... {/snippet}, {@render name(args)}
 * - Event attributes: onclick, onkeydown, oninput (replacing Svelte 4 on:click)
 * - Bindings: bind:value, bind:checked, bind:this
 * - Control flow: {#if}, {#each}, {#await}, {#key}
 */

export type Svelte5RuneKind =
  | "$state"
  | "$state.raw"
  | "$derived"
  | "$derived.by"
  | "$effect"
  | "$effect.pre"
  | "$effect.root"
  | "$props"
  | "$bindable"
  | "$inspect"
  | "$host";

export interface Svelte5PropRune {
  name: string;
  typeAnnotation?: string;
  defaultValue?: string;
  isBindable: boolean;
}

export interface Svelte5StateRune {
  name: string;
  isRaw: boolean;
  initialValueExpr: string;
  typeAnnotation?: string;
}

export interface Svelte5DerivedRune {
  name: string;
  isDerivedBy: boolean; // $derived.by(() => { ... })
  expressionOrBody: string;
  typeAnnotation?: string;
}

export interface Svelte5EffectRune {
  id: string;
  effectKind: "$effect" | "$effect.pre" | "$effect.root";
  bodyCode: string;
  hasCleanup: boolean;
  cleanupCode?: string;
}

export interface Svelte5SnippetParam {
  name: string;
  typeAnnotation?: string;
  defaultValue?: string;
}

export interface Svelte5Snippet {
  name: string;
  parameters: any;
  bodyNodes: Svelte5TemplateNode[];
}

export type Svelte5TemplateNodeKind =
  | "element"
  | "text"
  | "expression_tag"
  | "render_tag" // {@render snippet(args)}
  | "html_tag"   // {@html rawHtml}
  | "const_tag"  // {@const x = y}
  | "debug_tag"  // {@debug x}
  | "if_block"
  | "each_block"
  | "await_block"
  | "key_block"
  | "snippet_definition"
  | "component";

export interface Svelte5Attribute {
  name: string;
  value: string;
  isDynamic: boolean;
  isBinding?: boolean; // bind:value
  isEventHandler?: boolean; // onclick
  modifiers?: string[];
}

export interface Svelte5TemplateNode {
  id: string;
  kind: Svelte5TemplateNodeKind;
  tag?: string; // 'div', 'Button', 'Text', etc.
  attributes?: any;
  events: Record<string, string>;
  text?: string;
  expression?: string;
  
  // For {@render snippetName(args)}
  renderSnippet?: {
    snippetName: string;
    args: string[];
  };

  // For {#if test} ... {:else if} ... {:else} ... {/if}
  ifBlock?: {
    testExpr: string;
    consequent: Svelte5TemplateNode[];
    alternate?: Svelte5TemplateNode[];
    elseIfBranches?: {
      testExpr: string;
      consequent: Svelte5TemplateNode[];
    }[];
  };

  // For {#each items as item, index (key)} ... {:else} ... {/each}
  eachBlock?: {
    sourceExpr: string;
    itemName: string;
    indexName?: string;
    keyExpr?: string;
    body: Svelte5TemplateNode[];
    emptyBody?: Svelte5TemplateNode[];
  };

  // For {#await promise} ... {:then value} ... {:catch error} ... {/await}
  awaitBlock?: {
    promiseExpr: string;
    pendingBody?: Svelte5TemplateNode[];
    thenValueName?: string;
    thenBody?: Svelte5TemplateNode[];
    catchErrorName?: string;
    catchBody?: Svelte5TemplateNode[];
  };

  children: Svelte5TemplateNode[];
}

export interface Svelte5ComponentAst {
  componentName: string;
  name: string;
  success: boolean;
  component: Svelte5ComponentAst;
  props: Svelte5PropRune[];
  states: Svelte5StateRune[];
  derived: Svelte5DerivedRune[];
  effects: Svelte5EffectRune[];
  snippets: Svelte5Snippet[];
  runes: { runeKind: string; identifier: string }[];
  functions: { name: string }[];
  methods: {
    name: string;
    parameters: { name: string; type?: string }[];
    returnType?: string;
    bodyCode: string;
    isAsync: boolean;
  }[];
  templateRoot: Svelte5TemplateNode[];
  templateElements: Svelte5TemplateNode[];
  cssScopedStyle?: string;
  moduleScript?: string;
  isTs: boolean;
}

export type Svelte5ComponentDecl = Svelte5ComponentAst;
