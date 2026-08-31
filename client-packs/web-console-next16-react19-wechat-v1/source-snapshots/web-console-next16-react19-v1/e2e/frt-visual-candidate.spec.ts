import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

test("capture unapproved FRT visual candidates outside the baseline root", async ({ page }, testInfo) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.goto("/frontend");
  await expect(page.getByRole("heading", { name: "前端仓库转换工厂" })).toBeVisible();
  const defaultPath = testInfo.outputPath("candidate-frontend-default-zh-light.png");
  await page.screenshot({ path: defaultPath, fullPage: true, animations: "disabled" });

  await page.getByLabel("源技术栈").selectOption("React");
  await page.getByLabel("目标技术栈").selectOption("Flutter");
  const routePath = testInfo.outputPath("candidate-frontend-react-to-flutter-zh-light.png");
  await page.screenshot({ path: routePath, fullPage: true, animations: "disabled" });
  await writeFile(testInfo.outputPath("CANDIDATE-NOT-APPROVED.json"), `${JSON.stringify({
    schema_version: 1,
    state: "CANDIDATE_NOT_APPROVED",
    project: testInfo.project.name,
    baseline_promotion_allowed: false,
  }, null, 2)}\n`);
});
