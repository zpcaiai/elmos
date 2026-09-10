import { FullSyntaxFrontendTranspiler } from '../src/full-syntax-ast/full-syntax-transpiler-facade';

describe('Full-Syntax Frontend AST Transpiler Engine', () => {
  const transpiler = new FullSyntaxFrontendTranspiler();

  describe('Source: React (TSX / JSX)', () => {
    const reactSource = `
      import React, { useState, useEffect } from 'react';

      interface UserCardProps {
        userId: string;
        title?: string;
        onSelect?: (id: string) => void;
      }

      export function UserCard({ userId, title = "Default Title", onSelect }: UserCardProps) {
        const [active, setActive] = useState(false);
        const [count, setCount] = useState(0);

        useEffect(() => {
          console.log("Mounted with user", userId);
        }, [userId]);

        const handleClick = () => {
          setActive(!active);
          setCount(count + 1);
          if (onSelect) onSelect(userId);
        };

        return (
          <div className="user-card" onClick={handleClick}>
            <h3 className="card-title">{title}</h3>
            <p className="card-info">User ID: {userId}</p>
            <span className={active ? "status-active" : "status-idle"}>
              {active ? "Active" : "Inactive"} (Count: {count})
            </span>
          </div>
        );
      }
    `;

    it('transpiles React to Vue 3 SFC', () => {
      const result = transpiler.transpile(reactSource, 'react', 'vue3', { componentNameHint: 'UserCard' });
      expect(result.success).toBe(true);
      const vueSfc = result.outputFiles['UserCard.vue'];
      expect(vueSfc).toBeDefined();
      expect(vueSfc).toContain('<script setup lang="ts">');
      expect(vueSfc).toContain('defineProps<{');
      expect(vueSfc).toContain('ref<any>(false)');
      expect(vueSfc).toContain('ref<any>(0)');
      expect(vueSfc).toContain('<template>');
      expect(vueSfc).toContain('class="user-card"');
    });

    it('transpiles React to WeChat MiniApp 4-file bundle', () => {
      const result = transpiler.transpile(reactSource, 'react', 'miniprogram', { componentNameHint: 'UserCard' });
      expect(result.success).toBe(true);
      expect(result.outputFiles['index.wxml']).toBeDefined();
      expect(result.outputFiles['index.js']).toBeDefined();
      expect(result.outputFiles['index.wxss']).toBeDefined();
      expect(result.outputFiles['index.json']).toBeDefined();

      const wxml = result.outputFiles['index.wxml']!;
      expect(wxml).toContain('<view class="user-card"');
      expect(wxml).toContain('{{title}}');
      expect(wxml).toContain('{{userId}}');

      const js = result.outputFiles['index.js']!;
      expect(js).toContain('Component({');
      expect(js).toContain('properties:');
      expect(js).toContain('data:');
    });

    it('transpiles React to React functional TSX component', () => {
      const result = transpiler.transpile(reactSource, 'react', 'react', { componentNameHint: 'UserCard' });
      expect(result.success).toBe(true);
      const tsx = result.outputFiles['UserCard.tsx'];
      expect(tsx).toBeDefined();
      expect(tsx).toContain('export function UserCard');
      expect(tsx).toContain('useState');
      expect(tsx).toContain('className="user-card"');
    });
  });

  describe('Source: Vue 3 (<script setup> & Composition API)', () => {
    const vue3Source = `
      <template>
        <div class="counter-widget">
          <h2>{{ heading }}</h2>
          <button @click="increment">Click Count: {{ count }}</button>
          <p v-if="count > 5" class="milestone">High count reached!</p>
          <ul>
            <li v-for="tag in tags" :key="tag">{{ tag }}</li>
          </ul>
        </div>
      </template>

      <script setup lang="ts">
      import { ref, computed, onMounted } from 'vue';

      const props = withDefaults(defineProps<{
        heading: string;
        initialCount?: number;
      }>(), {
        initialCount: 0
      });

      const count = ref(props.initialCount);
      const tags = ref(['vue3', 'frontend', 'elmos']);

      function increment() {
        count.value++;
      }

      onMounted(() => {
        console.log("Widget mounted with", props.heading);
      });
      </script>

      <style scoped>
      .counter-widget { padding: 16px; }
      </style>
    `;

    it('transpiles Vue 3 to React TSX', () => {
      const result = transpiler.transpile(vue3Source, 'vue3', 'react', { componentNameHint: 'CounterWidget' });
      expect(result.success).toBe(true);
      const tsx = result.outputFiles['CounterWidget.tsx'];
      expect(tsx).toBeDefined();
      expect(tsx).toContain('export function CounterWidget');
      expect(tsx).toContain('className="counter-widget"');
    });

    it('transpiles Vue 3 to WeChat MiniApp', () => {
      const result = transpiler.transpile(vue3Source, 'vue3', 'miniprogram', { componentNameHint: 'CounterWidget' });
      expect(result.success).toBe(true);
      const wxml = result.outputFiles['index.wxml']!;
      expect(wxml).toContain('counter-widget');
      expect(wxml).toContain('{{heading}}');
      expect(wxml).toContain('{{count}}');
      expect(wxml).toContain('wx:for="{{tags}}"');
    });
  });

  describe('Source: Vue 2 (Options API)', () => {
    const vue2Source = `
      <template>
        <div class="profile-card">
          <span>{{ username }}</span>
          <button @click="toggleDetails">{{ showDetails ? 'Hide' : 'Show' }}</button>
          <div v-if="showDetails" class="details">
            <p>Bio: {{ bio }}</p>
          </div>
        </div>
      </template>

      <script>
      export default {
        name: 'ProfileCard',
        props: {
          username: { type: String, required: true },
          bio: { type: String, default: 'No bio' }
        },
        data() {
          return {
            showDetails: false
          };
        },
        methods: {
          toggleDetails() {
            this.showDetails = !this.showDetails;
          }
        },
        mounted() {
          console.log('Profile card ready');
        }
      };
      </script>
    `;

    it('transpiles Vue 2 Options API to Vue 3 <script setup>', () => {
      const result = transpiler.transpile(vue2Source, 'vue2', 'vue3', { componentNameHint: 'ProfileCard' });
      expect(result.success).toBe(true);
      const vueSfc = result.outputFiles['ProfileCard.vue'];
      expect(vueSfc).toContain('<script setup lang="ts">');
      expect(vueSfc).toContain('ref<any>(false)');
    });

    it('transpiles Vue 2 Options API to WeChat MiniApp', () => {
      const result = transpiler.transpile(vue2Source, 'vue2', 'miniprogram', { componentNameHint: 'ProfileCard' });
      expect(result.success).toBe(true);
      const wxml = result.outputFiles['index.wxml']!;
      expect(wxml).toContain('profile-card');
      expect(wxml).toContain('{{username}}');
      expect(wxml).toContain('wx:if="{{showDetails}}"');
    });
  });

  describe('Source: Angular (@Component)', () => {
    const angularSource = `
      import { Component, Input, Output, EventEmitter, OnInit } from '@angular/core';

      @Component({
        selector: 'app-alert-box',
        template: \`
          <div class="alert-box" *ngIf="visible">
            <h4>{{ title }}</h4>
            <p>{{ message }}</p>
            <button (click)="closeAlert()">Dismiss</button>
          </div>
        \`,
        styles: [\`.alert-box { border: 1px solid red; }\`]
      })
      export class AlertBoxComponent implements OnInit {
        @Input() title: string = 'Notice';
        @Input() message: string = '';
        @Output() dismissed = new EventEmitter<void>();

        visible: boolean = true;

        ngOnInit(): void {
          console.log('Alert box initialized');
        }

        closeAlert(): void {
          this.visible = false;
          this.dismissed.emit();
        }
      }
    `;

    it('transpiles Angular component to React TSX', () => {
      const result = transpiler.transpile(angularSource, 'angular', 'react', { componentNameHint: 'AlertBoxComponent' });
      expect(result.success).toBe(true);
      const tsx = result.outputFiles['AlertBoxComponent.tsx'];
      expect(tsx).toBeDefined();
      expect(tsx).toContain('export function AlertBoxComponent');
      expect(tsx).toContain('className="alert-box"');
    });

    it('transpiles Angular component to WeChat MiniApp', () => {
      const result = transpiler.transpile(angularSource, 'angular', 'miniprogram', { componentNameHint: 'AlertBox' });
      expect(result.success).toBe(true);
      const wxml = result.outputFiles['index.wxml']!;
      expect(wxml).toContain('alert-box');
      expect(wxml).toContain('wx:if="{{visible}}"');
    });
  });

  describe('Source: Svelte (SFC)', () => {
    const svelteSource = `
      <script>
        import { onMount } from 'svelte';

        export let label = 'Submit';
        export let disabled = false;

        let clickCount = 0;

        function handleClick() {
          if (!disabled) {
            clickCount += 1;
          }
        }

        onMount(() => {
          console.log('Svelte button mounted');
        });
      </script>

      <div class="svelte-btn-wrap">
        <button class="custom-btn" on:click={handleClick} disabled={disabled}>
          {label} ({clickCount})
        </button>
      </div>
    `;

    it('transpiles Svelte component to Vue 3', () => {
      const result = transpiler.transpile(svelteSource, 'svelte', 'vue3', { componentNameHint: 'CustomButton' });
      expect(result.success).toBe(true);
      const vueSfc = result.outputFiles['CustomButton.vue'];
      expect(vueSfc).toBeDefined();
      expect(vueSfc).toContain('<script setup lang="ts">');
      expect(vueSfc).toContain('custom-btn');
    });

    it('transpiles Svelte component to WeChat MiniApp', () => {
      const result = transpiler.transpile(svelteSource, 'svelte', 'miniprogram', { componentNameHint: 'CustomButton' });
      expect(result.success).toBe(true);
      const wxml = result.outputFiles['index.wxml']!;
      expect(wxml).toContain('custom-btn');
      expect(wxml).toContain('{{label}}');
    });
  });

  describe('Source: WeChat MiniApp (WXML + JS)', () => {
    const miniappSource = {
      wxml: `
        <view class="badge-container">
          <text class="badge-text">{{text}}</text>
          <view wx:if="{{showDot}}" class="badge-dot"></view>
          <slot></slot>
        </view>
      `,
      js: `
        Component({
          properties: {
            text: { type: String, value: '' },
            showDot: { type: Boolean, value: false }
          },
          data: {
            pressed: false
          },
          methods: {
            onTap() {
              this.setData({ pressed: !this.data.pressed });
            }
          }
        });
      `
    };

    it('transpiles WeChat MiniApp to React TSX', () => {
      const result = transpiler.transpile(miniappSource, 'miniprogram', 'react', { componentNameHint: 'Badge' });
      expect(result.success).toBe(true);
      const tsx = result.outputFiles['Badge.tsx'];
      expect(tsx).toBeDefined();
      expect(tsx).toContain('export function Badge');
      expect(tsx).toContain('className="badge-container"');
    });

    it('transpiles WeChat MiniApp to Vue 3 SFC', () => {
      const result = transpiler.transpile(miniappSource, 'miniprogram', 'vue3', { componentNameHint: 'Badge' });
      expect(result.success).toBe(true);
      const vueSfc = result.outputFiles['Badge.vue'];
      expect(vueSfc).toBeDefined();
      expect(vueSfc).toContain('<template>');
      expect(vueSfc).toContain('class="badge-container"');
    });
  });
});
