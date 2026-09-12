import {
  L5VisualInteractionOracle,
  DEFAULT_IPHONE_14_PRO,
} from "../src/l5-visual-interaction-oracle";
import * as path from "path";

describe("L5 Physical Device Pixel & Interactive State Machine Verification", () => {
  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  const targetProjectDir = path.join(
    repoRoot,
    "client-packs",
    "web-console-next16-react19-wechat-v1",
    "target-project"
  );

  const oracle = new L5VisualInteractionOracle(targetProjectDir);

  describe("Device Viewport & 2D Box-Model Rasterization", () => {
    it("configures standard iPhone 14 Pro viewport dimensions", () => {
      expect(DEFAULT_IPHONE_14_PRO.width).toBe(393);
      expect(DEFAULT_IPHONE_14_PRO.height).toBe(852);
      expect(DEFAULT_IPHONE_14_PRO.devicePixelRatio).toBe(3);
      expect(DEFAULT_IPHONE_14_PRO.deviceName).toBe("iPhone 14 Pro");
    });

    it("computes 2D box-model layout elements from WXML markup", () => {
      const mockWxml = `
        <view class="container" style="padding: 16px;">
          <view class="header" style="height: 48px; background-color: #2563eb;">
            <text class="title">Enterprise Cloud Console</text>
          </view>
          <view class="content" style="height: 200px; margin-top: 12px;">
            <text>System Operational</text>
            <button class="reload-btn" bindtap="handleReload">Refresh</button>
          </view>
        </view>
      `;

      const elements = oracle.computeLayoutElements(mockWxml);
      expect(elements.length).toBeGreaterThan(0);

      // Verify layout bounding boxes
      const root = elements[0]!;
      expect(root.x).toBe(0);
      expect(root.width).toBe(393);
      expect(root.height).toBeGreaterThan(0);
    });

    it("rasterizes virtual layout grid and calculates accurate pixel similarity", () => {
      const wxmlA = `<view style="height: 100px; background-color: #1e293b;"><text>Cluster Alpha</text></view>`;
      const wxmlB = `<view style="height: 100px; background-color: #1e293b;"><text>Cluster Alpha</text></view>`;
      const wxmlDifferent = `<view style="height: 300px; background-color: #ef4444;"><button>Error Alert</button></view>`;

      const gridA = oracle.rasterizeToVirtualGrid(oracle.computeLayoutElements(wxmlA));
      const gridB = oracle.rasterizeToVirtualGrid(oracle.computeLayoutElements(wxmlB));
      const gridDiff = oracle.rasterizeToVirtualGrid(oracle.computeLayoutElements(wxmlDifferent));

      // Identical layouts should yield 100% visual match rate
      const matchIdentical = oracle.compareVirtualScreenshots(gridA, gridB);
      expect(matchIdentical.visualMatchRate).toBe(1.0);
      expect(matchIdentical.meanSquaredError).toBe(0);
      expect(matchIdentical.structuralSimilarityIndex).toBe(1.0);
      expect(matchIdentical.pixelGatePassed).toBe(true);

      // Different layouts should detect divergence
      const matchDifferent = oracle.compareVirtualScreenshots(gridA, gridDiff);
      expect(matchDifferent.meanSquaredError).toBeGreaterThan(0);
      expect(matchDifferent.structuralSimilarityIndex).toBeLessThan(1.0);
    });
  });

  describe("Interactive Journey State Machine (TAP, Mutation, Teardown)", () => {
    it("simulates full interactive lifecycle journey for a component", async () => {
      const compRelDir = "components/CoverageMeter";
      const props = {
        label: "代码覆盖",
        status: "PASSED",
        passed: 10,
        total: 10,
        counts: { PASSED: 10, FAILED: 0, BLOCKED: 0, NOT_RUN: 0, UNKNOWN: 0, NOT_APPLICABLE: 0 },
      };

      const receipt = await oracle.verifyComponentInteractiveJourney("CoverageMeter", compRelDir, props);

      expect(receipt.componentName).toBe("CoverageMeter");
      expect(receipt.device.deviceName).toBe("iPhone 14 Pro");
      expect(receipt.l5Certified).toBe(true);

      // Check state transitions
      const transitions = receipt.transitions;
      expect(transitions.length).toBe(4);
      expect(transitions[0]?.stage).toBe("MOUNT");
      expect(transitions[0]?.status).toBe("SUCCEEDED");
      expect(transitions[1]?.stage).toBe("TAP_RELOAD");
      expect(transitions[1]?.status).toBe("SUCCEEDED");
      expect(transitions[2]?.stage).toBe("SET_DATA_MUTATION");
      expect(transitions[2]?.status).toBe("SUCCEEDED");
      expect(transitions[3]?.stage).toBe("TEARDOWN_LIFECYCLE");
      expect(transitions[3]?.status).toBe("SUCCEEDED");

      // Verify visual match rate exceeds the 99.0% threshold
      expect(receipt.pixelResult.visualMatchRate).toBeGreaterThanOrEqual(0.99);
      expect(receipt.pixelResult.pixelGatePassed).toBe(true);
    });
  });
});
