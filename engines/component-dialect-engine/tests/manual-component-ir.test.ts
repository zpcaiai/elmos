import { buildManualComponentIR } from "../src/manual-component-ir";
import { emitWechatHandPort, WECHAT_HAND_PORT_RUNTIME, WECHAT_PLATFORM_ADAPTERS } from "../src/wechat-hand-port";

const SOURCE = `
import styles from "./Dashboard.module.css";

export function Dashboard({ children, endpoint }: { children: React.ReactNode; endpoint: string }) {
  const [rows, setRows] = useState<Map<string, number>>(new Map());
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/dashboard", { signal: controller.signal }).then(() => setRows(new Map()));
    return () => controller.abort();
  }, [endpoint]);
  const visible = [...rows].filter((entry) => entry[1] > 0).map((entry) => entry[0]);
  return <table className={styles.table}><tbody><tr><td>{visible.join(",")}</td></tr></tbody>{children}</table>;
}
`;

describe("manual component semantic IR", () => {
  it("captures blocked semantics with exact trace and deterministic digest", () => {
    const input = {
      source: SOURCE,
      sourceFile: "app/Dashboard.tsx",
      componentName: "Dashboard",
      reasonCode: "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT",
      reason: "effect and derived collections need target lifecycle semantics",
      category: "effects-and-resources" as const,
    };
    const first = buildManualComponentIR(input);
    const second = buildManualComponentIR(input);
    expect(second).toEqual(first);
    expect(first.source.range.start).toBeGreaterThan(0);
    expect(first.source.range.end).toBeGreaterThan(first.source.range.start);
    expect(first.state).toEqual(expect.arrayContaining([expect.objectContaining({ name: "rows", type: "Map<string, number>" })]));
    expect(first.effects[0]).toMatchObject({ resources: ["NETWORK"], cleanup: "PRESENT", cancellationRequired: true });
    expect(first.collections.map((item) => item.operation)).toEqual(expect.arrayContaining(["Map", "filter", "map"]));
    expect(first.apiPaths).toEqual(["/api/dashboard"]);
    expect(first.platformSemantics).toEqual(expect.arrayContaining([
      expect.objectContaining({ domain: "TABLE", targetAdapter: "wechat-scroll-row-table-v1" }),
      expect.objectContaining({ domain: "SLOT", targetAdapter: "wechat-named-slot-projection-v1" }),
      expect.objectContaining({ domain: "CSS_MODULE", targetAdapter: "wechat-css-module-token-map-v1" }),
    ]));
    expect(first.targetPlan).toMatchObject({ disposition: "HAND_PORTED", runtimeEvidence: "NOT_RUN", certification: "NOT_CERTIFIED" });
    expect(first.irDigest).toMatch(/^sha256:[0-9a-f]{64}$/);
  });

  it("emits a native non-placeholder WeChat component and lifecycle runtime", () => {
    const ir = buildManualComponentIR({
      source: SOURCE,
      sourceFile: "app/Dashboard.tsx",
      componentName: "Dashboard",
      reasonCode: "CERTIFIED_COMPONENT_UNSUPPORTED_STATEMENT",
      reason: "blocked",
      category: "effects-and-resources",
    });
    const emitted = emitWechatHandPort(ir);
    expect(emitted.role).toBe("table");
    expect(emitted.files.js).toContain("createHandPortComponent");
    expect(emitted.files.wxml).toContain("scroll-view");
    expect(emitted.files.wxss).toContain("source-table");
    expect(Object.values(emitted.files).join("\n")).not.toContain("NOT TRANSLATED");
    expect(WECHAT_HAND_PORT_RUNTIME).toContain("task.abort()");
    expect(WECHAT_HAND_PORT_RUNTIME).toContain("epoch !== this.__requestEpoch");
    expect(WECHAT_HAND_PORT_RUNTIME).toContain("apiBaseUrl is required");
    expect(WECHAT_PLATFORM_ADAPTERS).toContain("NAVIGATION_PATH_NOT_ALLOWLISTED");
  });
});
