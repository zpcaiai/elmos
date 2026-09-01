import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

interface AcceptanceProfile {
  readonly performance: {
    readonly budgets: {
      readonly horizontal_overflow_pixels: number;
      readonly console_errors: number;
      readonly dom_content_loaded_ms: number;
      readonly load_event_ms: number;
      readonly cumulative_layout_shift: number;
      readonly resource_transfer_bytes: number;
    };
  };
}

interface VisualPolicy {
  readonly update_mode: "NONE";
  readonly max_diff_pixels: number;
  readonly pixel_threshold: number;
  readonly masks: readonly string[];
  readonly approval_required_before_comparison: boolean;
}

const repositoryRoot = path.resolve(__dirname, "../../..");
const packRoot = path.join(repositoryRoot, "client-packs/frt-g01-g30-platform");
const acceptance = JSON.parse(readFileSync(
  path.join(packRoot, "acceptance/acceptance-profile.json"),
  "utf8",
)) as AcceptanceProfile;
const visualPolicy = JSON.parse(readFileSync(
  path.join(packRoot, "visual-baselines/policy.json"),
  "utf8",
)) as VisualPolicy;

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
});

test("@visual approved baseline comparison is immutable and exact", async ({ page }) => {
  expect(visualPolicy).toMatchObject({
    update_mode: "NONE",
    max_diff_pixels: 0,
    pixel_threshold: 0,
    masks: [],
    approval_required_before_comparison: true,
  });
  await page.goto("/frontend");
  await expect(page.getByRole("heading", { name: "前端仓库转换工厂" })).toBeVisible();
  await expect(page).toHaveScreenshot("frontend-default-zh-light.png", { fullPage: true });

  await page.getByLabel("源技术栈").selectOption("React");
  await page.getByLabel("目标技术栈").selectOption("Flutter");
  await expect(page.getByRole("heading", { name: "React → Flutter" })).toBeVisible();
  await expect(page).toHaveScreenshot("frontend-react-to-flutter-zh-light.png", { fullPage: true });

  await page.getByRole("button", { name: "将导航和帮助切换为英文" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page).toHaveScreenshot("frontend-react-to-flutter-en-light.png", { fullPage: true });
});

test("semantic, keyboard, network and performance budgets remain jointly green", async ({ page }) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => failedRequests.push(request.url()));
  await page.addInitScript(() => {
    const state = window as unknown as { __frtCumulativeLayoutShift: number };
    state.__frtCumulativeLayoutShift = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as LayoutShift;
        if (!shift.hadRecentInput) state.__frtCumulativeLayoutShift += shift.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  await page.goto("/frontend");
  const search = page.getByPlaceholder("搜索 ID、名称或能力…");
  await search.focus();
  await page.keyboard.type("FRT-1305");
  const skill = page.getByRole("button", { name: /FRT-1305/ });
  await skill.focus();
  await page.keyboard.press("Enter");
  await expect(skill).toHaveAttribute("aria-pressed", "true");
  expect(await new AxeBuilder({ page }).analyze()).toMatchObject({ violations: [] });

  const observations = await page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
    const state = window as unknown as { __frtCumulativeLayoutShift: number };
    return {
      domContentLoadedMs: navigation.domContentLoadedEventEnd - navigation.startTime,
      loadEventMs: navigation.loadEventEnd - navigation.startTime,
      cumulativeLayoutShift: state.__frtCumulativeLayoutShift,
      resourceTransferBytes: performance.getEntriesByType("resource")
        .reduce((total, entry) => total + (entry as PerformanceResourceTiming).transferSize, 0),
      horizontalOverflowPixels: Math.max(
        0,
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
      ),
    };
  });
  const budgets = acceptance.performance.budgets;
  expect(observations.domContentLoadedMs).toBeLessThanOrEqual(budgets.dom_content_loaded_ms);
  expect(observations.loadEventMs).toBeLessThanOrEqual(budgets.load_event_ms);
  expect(observations.cumulativeLayoutShift).toBeLessThanOrEqual(budgets.cumulative_layout_shift);
  expect(observations.resourceTransferBytes).toBeLessThanOrEqual(budgets.resource_transfer_bytes);
  expect(observations.horizontalOverflowPixels).toBeLessThanOrEqual(budgets.horizontal_overflow_pixels);
  expect(consoleErrors).toHaveLength(budgets.console_errors);
  expect(failedRequests).toEqual([]);
});

interface LayoutShift extends PerformanceEntry {
  readonly hadRecentInput: boolean;
  readonly value: number;
}
