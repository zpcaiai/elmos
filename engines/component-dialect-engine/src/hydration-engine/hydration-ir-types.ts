/**
 * @file hydration-ir-types.ts
 * @description Universal Hydration & Rendering Strategy IR Contracts.
 * Models Island Architecture, selective client hydration, streaming SSR boundaries,
 * hydration mismatch diagnostics, and cross-framework micro-frontend bridges.
 * Conforms to Batch 32 Skill 1213 (b32-rendering-ssr-csr-hydration).
 */

export type HydrationStrategy =
  | 'client:load'      // Hydrate immediately upon page load
  | 'client:idle'      // Hydrate when main thread becomes idle (requestIdleCallback)
  | 'client:visible'   // Hydrate when component scrolls into viewport (IntersectionObserver)
  | 'client:media'     // Hydrate when CSS media query matches
  | 'client:only'      // Pure CSR, skip SSR entirely
  | 'server:static'    // Zero-JS static HTML, no hydration
  | 'server:streaming';// Streaming HTML with Suspense chunking

export type HydrationMismatchKind =
  | 'text-content-divergence'
  | 'attribute-divergence'
  | 'timestamp-drift'
  | 'random-id-mismatch'
  | 'client-only-node-missing'
  | 'server-tag-mismatch'
  | 'unstable-class-name';

export interface HydrationBoundaryIR {
  id: string;
  componentName: string;
  strategy: HydrationStrategy;
  entryFilePath: string;
  mediaQueryCondition?: string;
  viewportMargin?: string; // e.g. "200px"
  fallbackHtml?: string;
  props: Record<string, unknown>;
  priority: number; // 1 (highest) to 10 (lowest)
}

export interface HydrationMismatchRecord {
  id: string;
  kind: HydrationMismatchKind;
  domPath: string;
  serverValue: string;
  clientValue: string;
  suggestedRepair: 'suppressHydrationWarning' | 'move-to-useEffect' | 'pass-from-server' | 'replace-with-stable-seed';
  isFatal: boolean;
  explanation: string;
}

export interface IslandArchitectureIR {
  documentId: string;
  staticHtmlShell: string;
  islands: HydrationBoundaryIR[];
  scriptLoaderBundle: string;
  streamingEnabled: boolean;
  preloadLinks: string[];
}

export interface MicroFrontendBridgeConfig {
  islandId: string;
  componentName: string;
  sourceFramework: 'react' | 'vue' | 'svelte' | 'angular';
  targetHostFramework: 'wechat-miniapp' | 'custom-elements' | 'arkui';
  customTag: string;
  observedAttributes: string[];
  emittedEvents: string[];
}
