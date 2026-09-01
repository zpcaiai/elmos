import { expect, test } from "@playwright/test";

test.describe("本地运行与云部署指导", () => {
  test("多语言项目按已选目标展示配置和推荐平台", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "部署指导契约在 Chromium 执行一次");
    const capabilityResponse = await page.request.get("/api/capabilities/generation");
    expect(capabilityResponse.ok()).toBeTruthy();
    const capability = await capabilityResponse.json() as {
      deploymentGuidance: { status: string; externalEvidence: string; localProfiles: unknown[] };
    };
    expect(capability.deploymentGuidance.status).toBe("CONFIGURATION_REQUIRED");
    expect(capability.deploymentGuidance.externalEvidence).toBe("NOT_RUN");
    expect(capability.deploymentGuidance.localProfiles).toHaveLength(8);

    await page.goto("/generation");

    const guide = page.locator("section.runtime-deployment-guide")
      .filter({ has: page.locator("#generation-runtime-deployment-title") });
    await expect(guide.getByRole("heading", { name: "本地运行与云部署" })).toBeVisible();
    await expect(guide.getByText("Google Cloud Run", { exact: true }).first()).toBeVisible();
    await expect(guide.getByText("Java 21", { exact: true })).toBeVisible();
    await expect(guide.getByText("Python 3.12", { exact: true })).toBeVisible();
    await expect(guide.getByText("Rust 1.89", { exact: true })).toHaveCount(0);
    await expect(guide.getByText("外部执行仍为 NOT_RUN")).toBeHidden();

    await guide.locator("details.cloud-run-details > summary").click();
    await expect(guide.getByText("部署前必须补齐")).toBeVisible();
    await expect(guide.getByText("外部执行仍为 NOT_RUN")).toBeVisible();
    await expect(guide.locator("pre").filter({ hasText: "--no-allow-unauthenticated" })).toBeVisible();
  });

  test("Spring 翻新展示双工具链硬件与迁移后运行步骤", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "部署指导契约在 Chromium 执行一次");
    const capabilityResponse = await page.request.get("/api/capabilities/spring");
    expect(capabilityResponse.ok()).toBeTruthy();
    const capability = await capabilityResponse.json() as {
      deploymentGuidance: { status: string; externalEvidence: string };
    };
    expect(capability.deploymentGuidance.status).toBe("CONFIGURATION_REQUIRED");
    expect(capability.deploymentGuidance.externalEvidence).toBe("NOT_RUN");

    await page.goto("/spring");

    const guide = page.locator("section.runtime-deployment-guide")
      .filter({ has: page.locator("#spring-runtime-deployment-title") });
    await expect(guide.getByRole("heading", { name: "本地运行与云部署" })).toBeVisible();
    await expect(guide.getByText("Spring Boot 3.5.3", { exact: true })).toBeVisible();

    await guide.locator("details.runtime-profile > summary").click();
    await expect(guide.getByText("JDK 17 + JDK 21 / Maven 3.9.11 / OpenRewrite 6.35.0")).toBeVisible();
    await expect(guide.getByText("8 vCPU · 16 GB RAM · 40 GB 磁盘").last()).toBeVisible();
    await expect(guide.getByText("mvn -B -ntp verify", { exact: false })).toBeVisible();
  });
});
