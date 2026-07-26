import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const businessLine of [
  {
    path: "/spring",
    heading: "Java / Spring 老项目一键迁移",
    readyText: "完整真实旅程",
  },
  {
    path: "/translation",
    heading: "全库跨语言转换",
    readyText: "选择源语言与目标语言",
  },
] as const) {
  test(`${businessLine.heading} 在桌面与移动视口可操作且通过自动可访问性检查`, async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });

    await page.goto(businessLine.path);
    await expect(page.getByRole("heading", { name: businessLine.heading })).toBeVisible();
    await expect(page.getByText(businessLine.readyText, { exact: true })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
}

test("跨语言整库范围只保存发现与拆分交接，不伪造执行结果", async ({ page }) => {
  await page.goto("/translation");
  await page.getByLabel("仓库引用").fill("local:e2e-customer-repository");
  await page.getByLabel("评估范围").selectOption("repository");
  await page.getByRole("button", { name: "保存路线交接" }).click();
  await expect(page.getByText("整个仓库必须先导入与当前仓库引用", { exact: false })).toBeVisible();

  const digest = "a".repeat(64);
  await page.getByLabel("导入仓库清单 JSON").setInputFiles({
    name: "repository-route-plan.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify({
      schema_version: "1.0.0",
      kind: "elmos.repository-route-plan",
      status: "PLANNED",
      repository_ref: "local:e2e-customer-repository",
      snapshot_sha256: digest,
      snapshot_consistency: "STABLE_READ_ONLY_SCAN",
      route_id: "java-to-python",
      source_language: "java",
      target_language: "python",
      file_count: 1,
      source_file_count: 1,
      source_bytes: 128,
      language_counts: { java: 1, csharp: 0, python: 0, typescript: 0 },
      ignored_symlink_count: 0,
      work_units: [{
        id: "WU-00001",
        route_id: "java-to-python",
        source_path: "src/main/java/example/Order.java",
        source_sha256: digest,
        source_bytes: 128,
        status: "DISCOVERY_REQUIRED",
        execution_status: "NOT_RUN",
        required_inputs: ["function_name", "behavior_cases_json"],
        declared_profile: "typed-pure-function-v1",
        unsupported_until_discovered: ["object_graph", "database"],
      }],
      execution_status: "NOT_RUN",
      external_verification_status: "NOT_RUN",
      certification_status: "NOT_CERTIFIED",
      limitations: ["Repository-wide success is not inferred."],
    })),
  });
  await expect(page.getByText("已验证只读清单：1 个源文件拆为 1 个待发现工作单元。")).toBeVisible();
  await page.getByRole("button", { name: "保存路线交接" }).click();
  await expect(page.getByText("整库路线交接已绑定 1 个工作单元；转换执行仍为 NOT_RUN。")).toBeVisible();
  await expect(page.getByText("清单只读取受支持源文件", { exact: false })).toBeVisible();
});
