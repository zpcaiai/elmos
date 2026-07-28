import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("多语言项目生成 UI", () => {
  test("跨浏览器呈现、键盘焦点与自动可访问性检查", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });

    await page.goto("/generation");
    await expect(page.getByRole("heading", { name: "多语言项目生成" })).toBeVisible();
    await expect(page.getByText("Java 21", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Rust 1.89.0", { exact: true }).first()).toBeVisible();

    await page.keyboard.press("Tab");
    const focusedTag = await page.evaluate(() => document.activeElement?.tagName ?? "");
    expect(["A", "BUTTON", "INPUT"]).toContain(focusedTag);

    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(accessibility.violations).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });

  test("移动视口没有横向溢出且关键操作可触达", async ({ page }, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("mobile-"), "移动布局只在声明的移动项目执行");
    await page.goto("/generation");
    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
    await expect(page.getByRole("button", { name: "锁定生成计划" })).toBeVisible();
  });

  test("错误凭证失败关闭且不能绕过需求审阅", async ({ page }) => {
    await page.goto("/generation");
    await page.getByLabel("本地 Runner 令牌").fill("incorrect-browser-token-000000");
    await page.getByRole("button", { name: "锁定生成计划" }).click();
    await page.getByRole("button", { name: "分析并整理需求" }).click();
    await expect(page.getByText("需求分析被阻断：AUTHENTICATION_REQUIRED")).toBeVisible();
    await expect(
      page.getByRole("checkbox", { name: /我已审阅结构化需求/ }),
    ).toBeDisabled();
    await expect(page.getByRole("button", { name: "执行并验证" })).toBeDisabled();
  });

  test("企业配置只开放携带集成证据的单目标 PostgreSQL JWT/OIDC 组合", async ({ page }) => {
    await page.goto("/generation");
    await expect(page.getByLabel("数据配置").locator('option[value="postgresql"]')).toHaveText(
      "PostgreSQL 17.5 生产配置",
    );
    await page.getByLabel("数据配置").selectOption("postgresql");

    const target = (label: string) =>
      page.locator("label.target-card").filter({ hasText: label }).locator('input[type="checkbox"]');
    // Only targets whose production evidence the repository can reproduce are
    // selectable; every other target stays disabled.
    await expect(target("Python 3.12")).toBeChecked();
    for (const label of [
      "Java 21",
      "Go 1.25.0",
      "TypeScript Node 26.0.0",
      "C# .NET 10.0.301",
      "Kotlin 2.2.20 / JVM 21",
      "Rust 1.89.0",
      "PHP 8.4.12",
    ]) {
      await expect(target(label)).toBeEnabled();
    }
    await expect(page.getByLabel("认证配置")).toHaveValue("jwt");

    // The production profile is verified one target at a time, so selection
    // replaces rather than accumulates.
    await target("Go 1.25.0").click();
    await expect(target("Go 1.25.0")).toBeChecked();
    await expect(target("Python 3.12")).not.toBeChecked();

    await page.getByLabel("认证配置").selectOption("oidc");
    await expect(page.getByLabel("认证配置")).toHaveValue("oidc");
    await page.getByRole("button", { name: "锁定生成计划" }).click();
    await expect(page.locator(".preview-target-list").getByText("Go 1.25.0", { exact: true })).toBeVisible();
    await expect(page.locator(".preview-target-list").getByText("Python 3.12", { exact: true })).toHaveCount(0);
  });

  test("刷新后可用精确身份与任务 UUID 恢复持久化任务", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "任务恢复契约只需在 Chromium 执行一次");
    const jobId = "123e4567-e89b-42d3-a456-426614174000";
    let observedHeaders: Record<string, string> = {};
    await page.route(`**/api/generation/jobs/${jobId}`, async (route) => {
      observedHeaders = {
        tenant: route.request().headers()["x-elmos-tenant"] ?? "",
        actor: route.request().headers()["x-elmos-actor"] ?? "",
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: jobId,
          tenantId: "tenant-recovery",
          actor: "user:recovery-reviewer",
          createdAt: "2026-07-26T10:00:00Z",
          updatedAt: "2026-07-26T10:05:00Z",
          status: "COMPLETED",
          stage: "complete",
          progress: 100,
          resultStatus: "PASSED",
          artifactReady: false,
          artifacts: [],
          logs: [{ at: "2026-07-26T10:05:00Z", stream: "system", message: "Recovered persisted job." }],
          runtime: {
            status: "STOPPED",
            language: "java",
            plans: [{
              language: "java",
              cwd: "/runner/workspace/java",
              command: ["java", "-jar", "app.jar"],
              environment: { HOST: "127.0.0.1" },
              port: 8081,
            }],
            updatedAt: "2026-07-26T10:05:00Z",
          },
        }),
      });
    });

    await page.goto("/generation");
    await page.getByLabel("租户标识").fill("tenant-recovery");
    await page.getByLabel("审批者").fill("user:recovery-reviewer");
    await page.getByLabel("本地 Runner 令牌").fill("short-lived-recovery-token");
    await page.getByLabel("恢复任务 ID").fill(jobId);
    await page.getByRole("button", { name: "恢复任务" }).click();

    await expect(page.getByText("已按租户与操作者身份恢复任务 123e4567", { exact: false })).toBeVisible();
    await expect(page.getByText("123e4567", { exact: true })).toBeVisible();
    await expect(page.getByText("PASSED", { exact: true })).toBeVisible();
    expect(observedHeaders).toEqual({
      tenant: "tenant-recovery",
      actor: "user:recovery-reviewer",
    });
  });
});
