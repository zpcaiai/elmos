import {
  createVirtualBOM,
  EnterpriseThirdPartyAdapter,
  React19RscMiniAppBridge,
  CssInJsCompiler,
} from "../src/runtime/enterprise-web-polyfill";
import * as React from "react";

describe("Enterprise Web Polyfill Layer (Dead End Elimination)", () => {
  describe("Dead End 1: Virtual BOM & Observers", () => {
    it("provides standard window, document, location, and storage primitives", () => {
      const bom = createVirtualBOM({ url: "https://enterprise.example.com/dashboard" });

      expect(bom.window.innerWidth).toBe(393);
      expect(bom.window.innerHeight).toBe(852);
      expect(bom.window.devicePixelRatio).toBe(3);
      expect(bom.location.href).toBe("https://enterprise.example.com/dashboard");
      expect(bom.location.pathname).toBe("/dashboard");
      expect(bom.location.hostname).toBe("enterprise.example.com");

      // Storage
      bom.localStorage.setItem("authToken", "jwt-12345");
      expect(bom.localStorage.getItem("authToken")).toBe("jwt-12345");
      expect(bom.localStorage.length).toBe(1);
      bom.localStorage.removeItem("authToken");
      expect(bom.localStorage.getItem("authToken")).toBeNull();

      // matchMedia
      const mql = bom.window.matchMedia("(max-width: 600px)");
      expect(mql.matches).toBe(true);

      // Animation frames
      const cb = jest.fn();
      const id = bom.window.requestAnimationFrame(cb);
      expect(typeof id).toBe("number");
      bom.window.cancelAnimationFrame(id);
    });

    it("supports ResizeObserver, IntersectionObserver, and MutationObserver without throwing", () => {
      const bom = createVirtualBOM();

      // ResizeObserver
      const roCallback = jest.fn();
      const ro = new bom.ResizeObserver(roCallback);
      const fakeElement = bom.document.createElement("div");
      ro.observe(fakeElement);
      expect(roCallback).toHaveBeenCalled();
      ro.unobserve(fakeElement);
      ro.disconnect();

      // IntersectionObserver
      const ioCallback = jest.fn();
      const io = new bom.IntersectionObserver(ioCallback);
      io.observe(fakeElement);
      expect(ioCallback).toHaveBeenCalled();
      io.disconnect();

      // MutationObserver
      const moCallback = jest.fn();
      const mo = new bom.MutationObserver(moCallback);
      mo.observe(fakeElement, { childList: true });
      mo.disconnect();
    });
  });

  describe("Dead End 2: Enterprise 3rd-Party Library Adapters", () => {
    it("EChartsAdapter creates canvas-compatible mock and registers options", () => {
      const echarts = EnterpriseThirdPartyAdapter.createEChartsMock();
      const container = { clientWidth: 400, clientHeight: 300 };
      const chart = echarts.init(container);

      const option = {
        title: { text: "Migration Quality" },
        xAxis: { type: "category", data: ["A", "B", "C"] },
        series: [{ type: "bar", data: [95, 98, 100] }],
      };

      chart.setOption(option);
      expect(chart.getOption()).toBe(option);
      expect(chart.getWidth()).toBe(400);

      chart.resize({ width: 500, height: 350 });
      expect(chart.getWidth()).toBe(500);

      chart.dispose();
      expect(chart.isDisposed()).toBe(true);
    });

    it("MonacoEditorAdapter provides complete editor mock API", () => {
      const monaco = EnterpriseThirdPartyAdapter.createMonacoMock();
      const model = monaco.editor.createModel("SELECT 1 FROM dual;", "sql");
      expect(model.getValue()).toBe("SELECT 1 FROM dual;");

      const editor = monaco.editor.create(null, { value: "INITIAL" });
      expect(editor.getValue()).toBe("INITIAL");
      editor.setValue("NEW_CODE");
      expect(editor.getValue()).toBe("NEW_CODE");

      editor.dispose();
    });

    it("AntdAndLucideAdapter creates valid SVG stub elements", () => {
      const IconComp = EnterpriseThirdPartyAdapter.createIconStub("CheckCircleOutlined", React);
      expect(IconComp.displayName).toBe("CheckCircleOutlined");

      const elem = IconComp({ size: 24, color: "green" });
      expect(elem.type).toBe("div");
      expect(elem.props["data-icon"]).toBe("CheckCircleOutlined");
      expect(elem.props.children).toBeDefined();
    });

    it("AxiosAdapter performs request routing with cancellation", async () => {
      const axios = EnterpriseThirdPartyAdapter.createAxiosMock();
      const res = await axios.get("https://api.example.com/status");

      expect(res.status).toBe(200);
      expect(res.statusText).toBe("OK");
      expect(res.data).toEqual({ status: "ok", mock: true });

      const controller = axios.CancelToken.source();
      controller.cancel("Request cancelled by test");
    });
  });

  describe("Dead End 3: React 19 RSC & Server Actions", () => {
    it("dispatches server action through WeChat bridge and returns payload", async () => {
      const mockAction = async (payload: { id: string }) => {
        return { success: true, receivedId: payload.id };
      };

      const result = await React19RscMiniAppBridge.dispatchServerAction(
        mockAction,
        { id: "action-42" },
        { actionId: "test-action" }
      );

      expect(result).toEqual({ success: true, receivedId: "action-42" });
    });

    it("provides action state hook dispatch and optimistic update states", async () => {
      const actionFn = async (state: { count: number }, delta: number) => {
        return { count: state.count + delta };
      };

      const [state, dispatch, isPending] = React19RscMiniAppBridge.createActionStateHook(
        actionFn,
        { count: 10 }
      );

      expect(state.count).toBe(10);
      expect(isPending).toBe(false);

      const next = await dispatch(5);
      expect(next.count).toBe(15);

      // Optimistic hook
      const [optState, updateOpt] = React19RscMiniAppBridge.createOptimisticHook(
        { value: "committed" },
        (_current: { value: string }, update: string) => ({ value: update })
      );

      expect(optState.value).toBe("committed");
      const temp = updateOpt("optimistic_preview");
      expect(temp.value).toBe("optimistic_preview");
    });
  });

  describe("Dead End 4: CSS-in-JS & Tailwind Dynamic Styles", () => {
    it("sanitizes Tailwind arbitrary and bracketed classes for WXML compatibility", () => {
      const raw = "p-[12px] bg-[#f0f0f0] flex flex-col md:grid w-1/2 hover:opacity-80";
      const sanitized = CssInJsCompiler.sanitizeClassName(raw);

      expect(sanitized).toBe("p--12px bg---f0f0f0 flex flex-col md_grid w-1_2 hover_opacity-80");
      expect(sanitized).not.toContain("[");
      expect(sanitized).not.toContain("]");
      expect(sanitized).not.toContain("#");
      expect(sanitized).not.toContain(":");
      expect(sanitized).not.toContain("/");
    });

    it("compiles React dynamic style objects to inline WXML style string", () => {
      const styleObj = {
        color: "rgb(33, 33, 33)",
        backgroundColor: "#ffffff",
        fontSize: 16,
        paddingTop: 12,
        opacity: 0.95,
      };

      const inline = CssInJsCompiler.compileDynamicStyle(styleObj);
      expect(inline).toBe("color:rgb(33, 33, 33);background-color:#ffffff;font-size:16px;padding-top:12px;opacity:0.95;");
    });
  });
});
