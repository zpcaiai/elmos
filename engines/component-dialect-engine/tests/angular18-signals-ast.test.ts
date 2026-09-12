/**
 * @file angular18-signals-ast.test.ts
 * @description Comprehensive Jest test suite for Angular 18 Signals AST parser,
 * semantic lowerer, and code emitter.
 * Conforms to Batch 32 Skills 1208 & 1209.
 */

import { Angular18SignalsParser } from '../src/full-syntax-ast/angular18/angular18-signals-parser';
import { Angular18SignalsEmitter } from '../src/full-syntax-ast/angular18/angular18-signals-emitter';
import { Angular18SemanticLowerer } from '../src/full-syntax-ast/angular18/angular18-semantic-lowering';
import { Angular18ComponentDecl } from '../src/full-syntax-ast/angular18/angular18-signals-types';

describe('Angular 18 Signals Full-Syntax AST Subsystem', () => {
  const parser = new Angular18SignalsParser();
  const emitter = new Angular18SignalsEmitter();
  const lowerer = new Angular18SemanticLowerer();

  const sampleAngular18 = `
import { Component, signal, computed, effect, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-user-profile',
  standalone: true,
  imports: [CommonModule],
  template: \`
    <div class="user-card">
      <h2>{{ displayName() }}</h2>
      @if (isAdmin()) {
        <span class="badge badge-admin">Administrator</span>
      } @else {
        <span class="badge">Standard User</span>
      }
      <p>Points: {{ score() }}</p>
      <button (click)="boostScore()">Boost</button>
    </div>
  \`,
})
export class UserProfileComponent {
  public username = input.required<string>();
  public role = input<string>('guest');
  public statusChanged = output<boolean>();

  public score = signal<number>(100);
  public isAdmin = computed(() => this.role() === 'admin');
  public displayName = computed(() => this.username().toUpperCase());

  constructor() {
    effect(() => {
      console.log('Score updated:', this.score());
    });
  }

  public boostScore(): void {
    this.score.update(v => v + 50);
    this.statusChanged.emit(true);
  }
}
`;

  it('should parse Angular 18 Standalone component metadata and Signals', () => {
    const res = parser.parse(sampleAngular18);
    expect(res.success).toBe(true);
    expect(res.component).toBeDefined();

    const comp = res.component as Angular18ComponentDecl;
    expect(comp.name).toBe('UserProfileComponent');
    expect(comp.selector).toBe('app-user-profile');
    expect(comp.standalone).toBe(true);

    // Inputs / Outputs
    expect(comp.inputs.some((i) => i.name === 'username')).toBe(true);
    expect(comp.inputs.some((i) => i.name === 'role')).toBe(true);
    expect(comp.outputs.some((o) => o.name === 'statusChanged')).toBe(true);

    // Signals
    const scoreSig = comp.signals.find((s) => s.name === 'score');
    expect(scoreSig).toBeDefined();
    expect(scoreSig?.kind).toBe('writable');

    const adminComputed = comp.signals.find((s) => s.name === 'isAdmin');
    expect(adminComputed).toBeDefined();
    expect(adminComputed?.kind).toBe('computed');

    const nameComputed = comp.signals.find((s) => s.name === 'displayName');
    expect(nameComputed).toBeDefined();
    expect(nameComputed?.kind).toBe('computed');

    // Methods
    expect(comp.methods.some((m) => m.name === 'boostScore')).toBe(true);
  });

  it('should parse built-in control flow (@if, @for, @switch) in template', () => {
    const res = parser.parse(sampleAngular18);
    const comp = res.component as Angular18ComponentDecl;

    expect(comp.controlFlowBlocks.length).toBeGreaterThan(0);
    const ifBlock = comp.controlFlowBlocks.find((b) => b.type === 'if');
    expect(ifBlock).toBeDefined();
    expect(ifBlock?.conditionCode).toBe('isAdmin()');
  });

  it('should lower Angular 18 Component to Universal Component IR', () => {
    const parseRes = parser.parse(sampleAngular18);
    const comp = parseRes.component as Angular18ComponentDecl;

    const universalIR = lowerer.lowerToUniversal(comp);
    expect(universalIR.sourceFramework).toBe('angular18');
    expect(universalIR.name).toBe('UserProfileComponent');
    expect(universalIR.stateVariables.some((v) => v.name === 'score')).toBe(true);
    expect(universalIR.props.some((p) => p.name === 'username')).toBe(true);
  });

  it('should lift Universal IR back to Angular 18 Component and emit clean standalone code', () => {
    const parseRes = parser.parse(sampleAngular18);
    const comp = parseRes.component as Angular18ComponentDecl;
    const universalIR = lowerer.lowerToUniversal(comp);

    const lifted = lowerer.liftFromUniversal(universalIR);
    const emittedCode = emitter.emit(lifted);

    expect(emittedCode).toContain('@Component');
    expect(emittedCode).toContain('standalone: true');
    expect(emittedCode).toContain('signal(');
    expect(emittedCode).toContain('computed(');
    expect(emittedCode).toContain('export class UserProfileComponent');
  });

  it('should parse @for block with track expression', () => {
    const forTemplateCode = `
import { Component, signal } from '@angular/core';

@Component({
  selector: 'app-item-list',
  standalone: true,
  template: \`
    <ul>
      @for (item of items(); track item.id) {
        <li>{{ item.name }}</li>
      } @empty {
        <li>No items</li>
      }
    </ul>
  \`,
})
export class ItemListComponent {
  public items = signal([{ id: 1, name: 'Item 1' }]);
}
`;

    const res = parser.parse(forTemplateCode);
    expect(res.success).toBe(true);
    const comp = res.component as Angular18ComponentDecl;
    const forBlock = comp.controlFlowBlocks.find((b) => b.type === 'for');
    expect(forBlock).toBeDefined();
    expect(forBlock?.trackExpression).toBe('item.id');
  });
});
