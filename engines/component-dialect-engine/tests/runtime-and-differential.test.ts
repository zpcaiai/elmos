import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { ReactMiniAppHookContext, createReactMiniAppBridge } from "../src/runtime/react-miniapp-runtime";
import { HeadlessMiniProgramSandbox } from "../src/miniapp-automator-sandbox";
import { DoubleBlindDifferentialOracle } from "../src/differential-oracle";

describe("React -> WeChat MiniProgram Runtime Polyfill Layer", () => {
  it("manages useState, batching and transactional updates correctly", async () => {
    let capturedData: Record<string, unknown> = {};
    const mockInstance = {
      properties: { title: "Test" },
      data: {},
      setData: jest.fn((patch: Record<string, unknown>, cb?: () => void) => {
        Object.assign(capturedData, patch);
        if (cb) cb();
      }),
      triggerEvent: jest.fn(),
    };

    const ctx = new ReactMiniAppHookContext(mockInstance);
    const [count, setCount] = ctx.useState(0);
    const [text, setText] = ctx.useState("initial");

    expect(count).toBe(0);
    expect(text).toBe("initial");

    // Call state updates
    setCount(1);
    setCount(2);
    setText("updated");

    // Before microtask flush, mockInstance.setData hasn't been called synchronously
    expect(mockInstance.setData).not.toHaveBeenCalled();

    // Await microtask flush
    await Promise.resolve();

    expect(mockInstance.setData).toHaveBeenCalledTimes(1);
    expect(capturedData).toEqual({
      _h0: 2,
      _h1: "updated",
    });
  });

  it("handles useEffect mounting, dependency tracking, and cleanup on unmount", async () => {
    const mockInstance = {
      properties: {},
      data: {},
      setData: jest.fn((p, cb) => cb && cb()),
      triggerEvent: jest.fn(),
    };

    const ctx = new ReactMiniAppHookContext(mockInstance);
    let effectRan = 0;
    let cleanupRan = 0;

    ctx.useEffect(() => {
      effectRan++;
      return () => {
        cleanupRan++;
      };
    }, []);

    // Effect shouldn't run before mount
    expect(effectRan).toBe(0);

    ctx.markMounted();
    expect(effectRan).toBe(1);
    expect(cleanupRan).toBe(0);

    // Unmount
    ctx.markUnmounted();
    expect(cleanupRan).toBe(1);
  });

  it("evaluates useMemo and useCallback with dependency caching", () => {
    const mockInstance = {
      properties: {},
      data: {},
      setData: jest.fn(),
      triggerEvent: jest.fn(),
    };

    const ctx = new ReactMiniAppHookContext(mockInstance);
    let calcCount = 0;
    const compute = (factor: number) => {
      return ctx.useMemo(() => {
        calcCount++;
        return factor * 10;
      }, [factor]);
    };

    expect(compute(2)).toBe(20);
    expect(calcCount).toBe(1);

    // Re-evaluating with same factor returns cached value without recomputing
    ctx.resetIndex();
    expect(compute(2)).toBe(20);
    expect(calcCount).toBe(1);

    // Re-evaluating with changed factor triggers computation
    ctx.resetIndex();
    expect(compute(3)).toBe(30);
    expect(calcCount).toBe(2);
  });
});

describe("Headless MiniProgram Sandbox & Zero First-Screen Error Invariant", () => {
  let tempProjDir: string;

  beforeEach(() => {
    tempProjDir = fs.mkdtempSync(path.join(os.tmpdir(), "wechat-test-proj-"));
    fs.mkdirSync(path.join(tempProjDir, "components", "sample-card"), { recursive: true });
    fs.mkdirSync(path.join(tempProjDir, "components", "broken-card"), { recursive: true });
  });

  afterEach(() => {
    fs.rmSync(tempProjDir, { recursive: true, force: true });
  });

  it("passes L3 mounting with 0 errors on valid component", () => {
    const compDir = path.join(tempProjDir, "components", "sample-card");
    fs.writeFileSync(
      path.join(compDir, "index.json"),
      JSON.stringify({ component: true })
    );
    fs.writeFileSync(
      path.join(compDir, "index.js"),
      `Component({
        properties: { label: { type: String, value: "Hello" } },
        data: { count: 42 },
        lifetimes: {
          attached() {
            this.setData({ count: 100 });
          }
        }
      });`
    );
    fs.writeFileSync(
      path.join(compDir, "index.wxml"),
      `<view class="card"><text>{{label}}</text><text>{{count}}</text></view>`
    );

    const sandbox = new HeadlessMiniProgramSandbox(tempProjDir);
    const res = sandbox.mountComponent("components/sample-card", { label: "Greetings" });

    expect(res.l3Status).toBe("PASSED");
    expect(res.errors).toHaveLength(0);
    expect(res.dataSnapshot.label).toBe("Greetings");
    expect(res.dataSnapshot.count).toBe(100);
    expect(res.renderedWxml).toContain("Greetings");
    expect(res.renderedWxml).toContain("100");
  });

  it("fails L3 mounting and reports exact error when attached throws", () => {
    const compDir = path.join(tempProjDir, "components", "broken-card");
    fs.writeFileSync(
      path.join(compDir, "index.json"),
      JSON.stringify({ component: true })
    );
    fs.writeFileSync(
      path.join(compDir, "index.js"),
      `Component({
        lifetimes: {
          attached() {
            throw new TypeError("Cannot read properties of undefined (reading 'crash')");
          }
        }
      });`
    );
    fs.writeFileSync(path.join(compDir, "index.wxml"), `<view></view>`);

    const sandbox = new HeadlessMiniProgramSandbox(tempProjDir);
    const res = sandbox.mountComponent("components/broken-card");

    expect(res.l3Status).toBe("FAILED");
    expect(res.errors.length).toBeGreaterThan(0);
    expect(res.errors[0]).toContain("Cannot read properties of undefined");
  });
});

describe("Double-Blind Differential Oracle (>95% Consistency Gate)", () => {
  let tempProjDir: string;

  beforeEach(() => {
    tempProjDir = fs.mkdtempSync(path.join(os.tmpdir(), "wechat-oracle-test-"));
    fs.mkdirSync(path.join(tempProjDir, "components", "status-badge"), { recursive: true });
  });

  afterEach(() => {
    fs.rmSync(tempProjDir, { recursive: true, force: true });
  });

  it("certifies L4 PASSED when React and MiniProgram rendered output match >= 95%", async () => {
    const compDir = path.join(tempProjDir, "components", "status-badge");
    fs.writeFileSync(
      path.join(compDir, "index.json"),
      JSON.stringify({ component: true })
    );
    fs.writeFileSync(
      path.join(compDir, "index.js"),
      `Component({
        properties: {
          status: { type: String, value: "Active" },
          code: { type: Number, value: 200 }
        }
      });`
    );
    fs.writeFileSync(
      path.join(compDir, "index.wxml"),
      `<view class="badge"><text class="status">{{status}}</text><text class="code">{{code}}</text></view>`
    );

    const reactJsx = `
      function StatusBadge(props) {
        return (
          <div className="badge">
            <span className="status">{props.status}</span>
            <span className="code">{props.code}</span>
          </div>
        );
      }
      exports.default = StatusBadge;
    `;

    const oracle = new DoubleBlindDifferentialOracle(tempProjDir);
    const result = await oracle.evaluateComponent(
      "StatusBadge",
      reactJsx,
      "components/status-badge",
      { status: "Active", code: 200 }
    );

    expect(result.l3Passed).toBe(true);
    expect(result.l4Passed).toBe(true);
    expect(result.consistencyScore).toBeGreaterThanOrEqual(0.95);
  });
});
