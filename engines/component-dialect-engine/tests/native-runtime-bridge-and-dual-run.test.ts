/**
 * Test Suite: Target Native Runtime Bridge & Real Dual-Run Verification (Pillars 3 & 4)
 * 
 * Tests:
 * 1. WeChatRuntimeBridge: Path-based dirty diff, microtask debounced setData, payload stats
 * 2. MiniAppStoragePolyfill: LRU caching and quota management
 * 3. MiniAppNavigationManager: 10-level page stack boundary protection
 * 4. EventNormalizationBridge: Touch coordinates, form inputs, propagation stopping
 * 5. RealChromeHeadlessRunner: 2D Box IoU calculation, dual-run execution, gate verdicts
 */

import { WeChatRuntimeBridge } from "../src/runtime/wechat-runtime-bridge";
import { MiniAppStoragePolyfill, MiniAppNavigationManager } from "../src/runtime/wechat-web-api-polyfills";
import { EventNormalizationBridge } from "../src/runtime/event-normalization-bridge";
import { RealChromeHeadlessRunner } from "../src/headless-differential-suite/real-chrome-headless-runner";
import { DOMNode, HeadlessBoxLayoutEngine } from "../src/headless-differential-suite/headless-browser-dom";
import { FullSyntaxComponentIR } from "../src/full-syntax-ast/types";

describe("Native Runtime Bridge & Real Dual-Run Verification Suite", () => {
  describe("1. WeChatRuntimeBridge (Microtask Dirty Diff Scheduler)", () => {
    it("computes minimal path-based dirty diffs for nested objects and arrays", () => {
      const mockInstance = {
        data: {
          user: { name: "Alice", profile: { age: 25, city: "Beijing" } },
          items: [{ id: 1, text: "A" }, { id: 2, text: "B" }],
          counter: 0,
        },
        setData: jest.fn(),
      };

      const bridge = new WeChatRuntimeBridge(mockInstance);

      const patch = bridge.computeDirtyDiff(mockInstance.data, {
        user: { name: "Alice", profile: { age: 26, city: "Beijing" } },
        items: [{ id: 1, text: "A" }, { id: 2, text: "B_Updated" }],
        counter: 1,
      });

      // Path-based dirty diff should target only changed fields
      expect(patch).toEqual({
        "user.profile.age": 26,
        "items[1].text": "B_Updated",
        counter: 1,
      });
    });

    it("batches multiple synchronous enqueueUpdate calls into a single microtask flush", async () => {
      let flushedData: any = null;
      let flushCount = 0;

      const mockInstance = {
        data: { a: 1, b: 2, c: 3 },
        setData: jest.fn((patch, cb) => {
          flushCount++;
          flushedData = patch;
          if (cb) cb();
        }),
      };

      const bridge = new WeChatRuntimeBridge(mockInstance);

      // Rapidly enqueue sequential updates
      bridge.enqueueUpdate({ a: 10 });
      bridge.enqueueUpdate({ b: 20 });
      bridge.enqueueUpdate({ c: 30 });

      // Before microtask runs, setData should NOT have been called yet
      expect(mockInstance.setData).not.toHaveBeenCalled();

      // Wait for microtask tick
      await Promise.resolve();

      expect(flushCount).toBe(1);
      expect(flushedData).toEqual({ a: 10, b: 20, c: 30 });
      expect(bridge.getStats().totalFlushes).toBe(1);
      expect(bridge.getStats().totalKeysPatched).toBe(3);
    });
  });

  describe("2. MiniAppStoragePolyfill", () => {
    it("stores and retrieves items with LRU eviction tracking", () => {
      const storage = new MiniAppStoragePolyfill();
      storage.setItem("key1", "value1");
      storage.setItem("key2", "value2");

      expect(storage.getItem("key1")).toBe("value1");
      expect(storage.getItem("key2")).toBe("value2");
      expect(storage.getItem("non_existent")).toBeNull();

      storage.removeItem("key1");
      expect(storage.getItem("key1")).toBeNull();

      storage.clear();
      expect(storage.length).toBe(0);
    });
  });

  describe("3. MiniAppNavigationManager", () => {
    it("protects against WeChat page stack limit crash by switching push to replace at depth 10", () => {
      const nav = new MiniAppNavigationManager();
      expect(nav.stackDepth).toBe(1);

      // Push 8 more pages (depth reaches 9)
      for (let i = 2; i <= 9; i++) {
        nav.push(`/pages/page${i}/index`);
      }
      expect(nav.stackDepth).toBe(9);

      // Push 10th page (depth reaches 10)
      nav.push("/pages/page10/index");
      expect(nav.stackDepth).toBe(10);
      expect(nav.currentRoute).toBe("/pages/page10/index");

      // Push 11th page: Should NOT exceed 10; should auto-replace current page
      nav.push("/pages/page11/index");
      expect(nav.stackDepth).toBe(10);
      expect(nav.currentRoute).toBe("/pages/page11/index");
    });
  });

  describe("4. EventNormalizationBridge", () => {
    it("normalizes MiniApp touch coordinates into W3C SyntheticEvent", () => {
      const rawWxEvent = {
        type: "tap",
        timeStamp: 123456,
        target: { id: "btn1", offsetLeft: 10, offsetTop: 20, dataset: { role: "action" } },
        currentTarget: { id: "btn1", offsetLeft: 10, offsetTop: 20, dataset: { role: "action" } },
        detail: { x: 150, y: 300 },
        touches: [
          { identifier: 1, clientX: 150, clientY: 300, pageX: 150, pageY: 300 }
        ]
      };

      const synthetic = EventNormalizationBridge.normalize(rawWxEvent);
      expect(synthetic.type).toBe("click");
      expect(synthetic.clientX).toBe(150);
      expect(synthetic.clientY).toBe(300);
      expect(synthetic.target.id).toBe("btn1");
      expect(synthetic.target.dataset.role).toBe("action");

      expect(synthetic.isPropagationStopped).toBe(false);
      synthetic.stopPropagation();
      expect(synthetic.isPropagationStopped).toBe(true);
    });

    it("normalizes MiniApp input form events with target.value", () => {
      const rawInputEvent = {
        type: "input",
        timeStamp: 123457,
        target: { id: "inputField", offsetLeft: 0, offsetTop: 0, dataset: {} },
        currentTarget: { id: "inputField", offsetLeft: 0, offsetTop: 0, dataset: {} },
        detail: { value: "Hello Elmos" }
      };

      const synthetic = EventNormalizationBridge.normalize(rawInputEvent);
      expect(synthetic.type).toBe("input");
      expect(synthetic.target.value).toBe("Hello Elmos");
    });
  });

  describe("5. RealChromeHeadlessRunner & 2D Box IoU", () => {
    it("computes 2D Box IoU across corresponding DOM nodes", () => {
      const webRoot = new DOMNode("element", "div");
      webRoot.computedLayout = {
        rect: { x: 0, y: 0, width: 375, height: 667 },
        display: "block",
        visibility: "visible",
      };

      const child1 = new DOMNode("element", "div");
      child1.computedLayout = {
        rect: { x: 10, y: 10, width: 100, height: 50 },
        display: "block",
        visibility: "visible",
      };
      webRoot.appendChild(child1);

      const miniAppRoot = new DOMNode("element", "view");
      miniAppRoot.computedLayout = {
        rect: { x: 0, y: 0, width: 375, height: 667 },
        display: "block",
        visibility: "visible",
      };

      const mChild1 = new DOMNode("element", "view");
      mChild1.computedLayout = {
        rect: { x: 10, y: 10, width: 100, height: 50 },
        display: "block",
        visibility: "visible",
      };
      miniAppRoot.appendChild(mChild1);

      const { averageIoU, matchedPairs } = RealChromeHeadlessRunner.calculateBoxIoU(webRoot, miniAppRoot);
      expect(matchedPairs).toBe(2);
      expect(averageIoU).toBe(1.0); // Exact match -> 100% IoU
    });

    it("executes dual-run verification for a component IR and verifies high DOM similarity", async () => {
      const testIR: FullSyntaxComponentIR = {
        schemaVersion: "2.0",
        componentName: "UserStatusCard",
        sourceFramework: "react",
        targetFramework: "miniprogram",
        props: [{ name: "userName", typeAnnotation: "string", defaultValue: '"Bob"', required: true, isCallback: false }],
        states: [{ name: "online", initialValueExpr: "true", typeAnnotation: "boolean" }],
        computed: [],
        effects: [],
        methods: [],
        slots: [],
        refs: [],
        templateRoot: {
          id: "root",
          kind: "element",
          tag: "div",
          attrs: [{ name: "class", value: "status-card", isDynamic: false }],
          children: [
            {
              id: "text_node",
              kind: "element",
              tag: "span",
              text: "User: Bob is Online",
            },
          ],
        },
        styles: { scopedCss: ".status-card { padding: 16px; }" },
        containerApis: [],
        thirdPartyComponents: [],
        rawSourceLinesCount: 20,
        metadata: {},
      };

      const miniappFiles = {
        "index.wxml": '<view class="status-card"><text>User: Bob is Online</text></view>',
        "index.js": 'Component({ data: { userName: "Bob", online: true } })',
        "index.wxss": ".status-card { padding: 32rpx; }",
      };

      const report = await RealChromeHeadlessRunner.executeDualRun(testIR, miniappFiles);
      expect(report.componentName).toBe("UserStatusCard");
      expect(report.metrics.structuralSimilarity).toBeGreaterThanOrEqual(0.95);
      expect(report.metrics.contentSimilarity).toBeGreaterThanOrEqual(0.95);
      expect(report.gateVerdict.passed).toBe(true);
      expect(report.gateVerdict.tier).toBe("L4_SEMANTIC_EQUIVALENT");
    });
  });
});
