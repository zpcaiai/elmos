/**
 * @file svelte5-runes-ast.test.ts
 * @description Comprehensive Jest test suite for Svelte 5 Runes AST parser,
 * semantic lowerer, and code emitter.
 * Conforms to Batch 32 Skills 1208 & 1209.
 */

import { Svelte5RunesParser } from '../src/full-syntax-ast/svelte5/svelte5-runes-parser';
import { Svelte5RunesEmitter } from '../src/full-syntax-ast/svelte5/svelte5-runes-emitter';
import { Svelte5SemanticLowerer } from '../src/full-syntax-ast/svelte5/svelte5-semantic-lowering';
import { Svelte5ComponentDecl } from '../src/full-syntax-ast/svelte5/svelte5-runes-types';

describe('Svelte 5 Runes Full-Syntax AST Subsystem', () => {
  const parser = new Svelte5RunesParser();
  const emitter = new Svelte5RunesEmitter();
  const lowerer = new Svelte5SemanticLowerer();

  const sampleSvelte5 = `
<script lang="ts">
  let { title = 'Default Title', initialCount = 0 } = $props<{ title?: string; initialCount?: number }>();

  let count = $state(initialCount);
  let doubleCount = $derived(count * 2);

  $effect(() => {
    console.log('Count changed:', count);
  });

  function increment() {
    count++;
  }

  function decrement() {
    count--;
  }
</script>

<div class="counter-container">
  <h2>{title}</h2>
  <p>Count: {count}, Double: {doubleCount}</p>
  <button onclick={decrement}>-</button>
  <button onclick={increment}>+</button>
</div>
`;

  it('should successfully parse Svelte 5 runes ($state, $derived, $effect, $props)', () => {
    const res = parser.parse(sampleSvelte5);
    expect(res.success).toBe(true);
    expect(res.component).toBeDefined();

    const comp = res.component as Svelte5ComponentDecl;
    expect(comp.name).toBe('Component');

    // Props
    expect(comp.props.length).toBe(2);
    expect(comp.props.find((p) => p.name === 'title')).toBeDefined();
    expect(comp.props.find((p) => p.name === 'initialCount')).toBeDefined();

    // Runes
    const stateRune = comp.runes.find((r) => r.runeKind === '$state');
    expect(stateRune).toBeDefined();
    expect(stateRune?.identifier).toBe('count');

    const derivedRune = comp.runes.find((r) => r.runeKind === '$derived');
    expect(derivedRune).toBeDefined();
    expect(derivedRune?.identifier).toBe('doubleCount');

    const effectRune = comp.runes.find((r) => r.runeKind === '$effect');
    expect(effectRune).toBeDefined();

    // Functions
    expect(comp.functions.some((f) => f.name === 'increment')).toBe(true);
    expect(comp.functions.some((f) => f.name === 'decrement')).toBe(true);
  });

  it('should parse template and modern onclick event bindings', () => {
    const res = parser.parse(sampleSvelte5);
    const comp = res.component as Svelte5ComponentDecl;

    expect(comp.templateElements.length).toBeGreaterThan(0);
    const rootDiv = comp.templateElements[0]!;
    expect(rootDiv.tag).toBe('div');
    expect(rootDiv.attributes['class']).toBe('counter-container');

    const buttons = rootDiv.children.filter((c) => c.tag === 'button');
    expect(buttons.length).toBe(2);
    expect(buttons[0]?.events['click']).toBe('decrement');
    expect(buttons[1]?.events['click']).toBe('increment');
  });

  it('should lower Svelte 5 AST to Universal Component IR', () => {
    const parseRes = parser.parse(sampleSvelte5);
    const svelteComp = parseRes.component as Svelte5ComponentDecl;

    const universalIR = lowerer.lowerToUniversal(svelteComp);
    expect(universalIR.sourceFramework).toBe('svelte5');
    expect(universalIR.stateVariables.some((v) => v.name === 'count')).toBe(true);
    expect(universalIR.props.some((p) => p.name === 'title')).toBe(true);
    expect(universalIR.templateRoot).toBeDefined();
  });

  it('should lift Universal IR back to Svelte 5 AST and emit valid Svelte 5 SFC', () => {
    const parseRes = parser.parse(sampleSvelte5);
    const svelteComp = parseRes.component as Svelte5ComponentDecl;
    const universalIR = lowerer.lowerToUniversal(svelteComp);

    const liftedComp = lowerer.liftFromUniversal(universalIR);
    const emittedSFC = emitter.emit(liftedComp);

    expect(emittedSFC).toContain('<script lang="ts">');
    expect(emittedSFC).toContain('$props');
    expect(emittedSFC).toContain('$state');
    expect(emittedSFC).toContain('onclick=');
    expect(emittedSFC).toContain('</script>');
  });

  it('should parse Svelte 5 {#snippet} blocks', () => {
    const snippetSvelte = `
<script lang="ts">
  let name = $state('Elmos');
</script>

{#snippet header(text)}
  <header class="card-header">
    <h3>{text}</h3>
  </header>
{/snippet}

<main>
  {@render header(name)}
</main>
`;

    const res = parser.parse(snippetSvelte);
    expect(res.success).toBe(true);
    const comp = res.component as Svelte5ComponentDecl;
    expect(comp.snippets.length).toBe(1);
    expect(comp.snippets[0]?.name).toBe('header');
    expect(comp.snippets[0]?.parameters).toContain('text');
  });
});
