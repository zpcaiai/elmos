import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { strToU8, zipSync } from "fflate";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 204, body: "" }));
});

function wordFixture(text: string): Buffer {
  const document = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>${text}</w:t></w:r></w:p><w:sectPr /></w:body>
</w:document>`;
  return Buffer.from(zipSync({
    "[Content_Types].xml": strToU8(`<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`),
    "_rels/.rels": strToU8(`<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`),
    "word/document.xml": strToU8(document),
    "word/_rels/document.xml.rels": strToU8(`<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>`),
  }));
}

function pdfFixture(text: string): Buffer {
  const escaped = text.replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
  const stream = `BT /F1 12 Tf 72 720 Td (${escaped}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream, "latin1")} >>\nstream\n${stream}\nendstream`,
  ];
  let result = "%PDF-1.4\n";
  const offsets = [0];
  for (const [index, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(result, "latin1"));
    result += `${index + 1} 0 obj\n${object}\nendobj\n`;
  }
  const xref = Buffer.byteLength(result, "latin1");
  result += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  result += offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("");
  result += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(result, "latin1");
}

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

  test("错误凭证失败关闭且不能绕过需求审阅", async ({ page, request }) => {
    const [capabilityResponse, readinessResponse, blockedResponse] = await Promise.all([
      request.get("/api/capabilities/generation"),
      request.get("/api/health?probe=readiness"),
      request.post("/api/generation/analyze", {
        headers: {
          "Authorization": "Bearer incorrect-browser-token-000000",
          "X-ELMOS-Tenant": "local-dev",
          "X-ELMOS-Actor": "user:reviewer",
        },
        data: {
          name: "order-service",
          namespace: "io.elmos.orders",
          description: "提供订单创建、查询与状态管理的服务",
          entity: "order",
          targets: ["java", "python"],
          persistence: "in-memory",
          authMode: "none",
        },
      }),
    ]);
    expect(capabilityResponse.status()).toBe(200);
    expect(readinessResponse.status()).toBe(200);
    expect(blockedResponse.status()).toBe(401);
    const capability = await capabilityResponse.json();
    const readiness = await readinessResponse.json();
    const blocked = await blockedResponse.json();
    expect(capability.localRunner.enabled).toBe(true);
    expect(readiness.localRunner.status).toBe("READY");
    expect(blocked).toEqual({
      status: "BLOCKED",
      reason: "AUTHENTICATION_REQUIRED",
    });

    await page.route("**/api/capabilities/generation", (route) =>
      route.fulfill({ status: 200, json: capability }));
    await page.route(/\/api\/health(?:\?.*)?$/, (route) =>
      route.fulfill({ status: 200, json: readiness }));
    let analyzeRequestObserved = false;
    await page.route("**/api/generation/analyze", async (route) => {
      const request = route.request();
      expect(request.method()).toBe("POST");
      expect(request.headers()["authorization"]).toBe(
        "Bearer incorrect-browser-token-000000",
      );
      expect(request.headers()["x-elmos-tenant"]).toBe("local-dev");
      expect(request.headers()["x-elmos-actor"]).toBe("user:reviewer");
      expect(request.postDataJSON()).toMatchObject({
        name: "order-service",
        namespace: "io.elmos.orders",
        entity: "order",
        targets: ["java", "python"],
        persistence: "in-memory",
        authMode: "none",
      });
      analyzeRequestObserved = true;
      await route.fulfill({ status: 401, json: blocked });
    });
    await page.goto("/generation");
    await expect(
      page.getByRole("region", { name: "项目生成能力摘要" })
        .getByText("READY", { exact: true }),
    ).toBeVisible({ timeout: 30_000 });
    const runnerToken = page.getByLabel("本地 Runner 令牌");
    await runnerToken.fill("incorrect-browser-token-000000");
    await expect(runnerToken).toHaveValue("incorrect-browser-token-000000");
    await page.getByRole("button", { name: "锁定生成计划" }).click();
    const analyze = page.getByRole("button", { name: "分析并整理需求" });
    await expect(analyze).toBeEnabled({ timeout: 30_000 });
    await analyze.focus();
    await expect(analyze).toBeFocused();
    await analyze.evaluate((button: HTMLButtonElement) => button.click());
    await expect.poll(() => page.evaluate(() =>
      (window as Window & { __generationAuthorization?: string })
        .__generationAuthorization ?? "",
    )).toBe("Bearer incorrect-browser-token-000000");
    await expect.poll(() => analyzeRequestObserved).toBe(true);
    await expect(page.getByText("需求分析被阻断：AUTHENTICATION_REQUIRED")).toBeVisible({
      timeout: 30_000,
    });
    await expect(
      page.getByRole("checkbox", { name: /我已审阅结构化需求/ }),
    ).toBeDisabled();
    await expect(page.getByRole("button", { name: "一键生成、验证并归档" })).toBeDisabled();
  });

  test("简述、TXT、Markdown、Word、HTML、PDF 与 Skill 可合并为哈希绑定来源包", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "多格式解析的代表旅程只执行一次");
    await page.goto("/generation");
    await page.getByLabel("审批者标识").fill("user:e2e");
    await page.getByLabel("租户标识").fill("local-e2e");
    await page.getByLabel("本地 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
    await page.getByLabel("项目说明").fill(
      "实体: order; order字段: reference:string:required; 权限: admin:create/read/update/delete:order",
    );
    await page.getByLabel("仓库 Skills").fill("elmos-project-synthesis");
    await page.getByLabel("上传需求文件").setInputFiles([
      { name: "requirements.txt", mimeType: "text/plain", buffer: Buffer.from("Order query requirement") },
      { name: "rules.md", mimeType: "text/markdown", buffer: Buffer.from("# Rules\nOrder status is reviewable.") },
      { name: "journey.html", mimeType: "text/html", buffer: Buffer.from("<main><h1>Journey</h1><p>Create an order.</p><script>ignored()</script></main>") },
      {
        name: "architecture.docx",
        mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer: wordFixture("Word architecture requirement"),
      },
      { name: "acceptance.pdf", mimeType: "application/pdf", buffer: pdfFixture("PDF acceptance requirement") },
    ]);

    await page.getByRole("button", { name: "解析并合并来源" }).click();

    const importedSources = page.locator(".generation-source-results");
    await expect(importedSources.getByText(/7 个来源/)).toBeVisible({ timeout: 30_000 });
    await expect(importedSources.getByText(/word-file · architecture.docx/)).toBeVisible();
    await expect(importedSources.getByText(/pdf-file · acceptance.pdf/)).toBeVisible();
    await expect(importedSources.getByText(/skill · elmos-project-synthesis/)).toBeVisible();
    await expect(page.getByLabel("项目说明")).toHaveValue(/Word architecture requirement/);
    await expect(page.getByLabel("项目说明")).toHaveValue(/PDF acceptance requirement/);
    await page.getByRole("button", { name: "锁定生成计划" }).click();
    await page.getByRole("button", { name: "分析并整理需求" }).click();
    await expect(page.getByText("实体与字段 · 1")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("来源证明 · 7")).toBeVisible();
    await expect(page.getByText("开放问题 · 0")).toBeVisible();
  });

  test("仓库工作区可一键交接为哈希绑定的项目生成来源", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "仓库到生成的代表旅程只执行一次");
    const workspaceId = "d12ac53a-30b8-4d87-8202-9c9a4b181cf8";
    let submittedBody = "";
    await page.route("**/api/generation/sources", async (route) => {
      submittedBody = route.request().postData() ?? "";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "READY_FOR_REVIEW",
          schemaVersion: "1.0.0",
          bundleSha256: "b".repeat(64),
          combinedText: "[来源 SRC-001 · repository-file · README.md]\n实体: order",
          sources: [{
            id: "SRC-001",
            kind: "repository-file",
            label: "README.md",
            mediaType: "text/markdown",
            origin: `workspace=${workspaceId};provider=GITEE;commit=${"1".repeat(40)};path=README.md`,
            sha256: "a".repeat(64),
            byteCount: 64,
            extractedCharacters: 64,
            includedCharacters: 64,
            truncated: false,
            warnings: [
              "REPOSITORY_WORKSPACE_CONTENT_IMPORTED_NOT_EXECUTED",
              "REMOTE_PUSH_PR_MERGE_AND_DEPLOYMENT_NOT_RUN",
            ],
          }],
          warnings: [
            "REMOTE_PUSH_PR_MERGE_AND_DEPLOYMENT_NOT_RUN",
            "REPOSITORY_WORKSPACE_CONTENT_IMPORTED_NOT_EXECUTED",
          ],
          extractedAt: "2026-07-28T00:00:00Z",
        }),
      });
    });

    await page.goto(`/generation?repositoryWorkspaceId=${workspaceId}`);
    await expect(page.getByLabel("代码仓库工作区 ID")).toHaveValue(workspaceId);
    await page.getByLabel("审批者标识").fill("user:e2e");
    await page.getByLabel("租户标识").fill("local-e2e");
    await page.getByLabel("本地 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
    await page.getByLabel("仓库来源文件（可选）").fill("README.md\ndocs/requirements.md");
    await page.getByRole("button", { name: "解析并合并来源" }).click();

    await expect(page.locator(".generation-source-results").getByText(/1 个来源/)).toBeVisible();
    await expect(page.locator(".generation-source-results").getByText(/repository-file · README.md/)).toBeVisible();
    expect(submittedBody).toContain(workspaceId);
    expect(submittedBody).toContain("README.md");
    expect(submittedBody).toContain("docs/requirements.md");
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

  test("多实体生产需求会在批准前显示单实体目标边界", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "能力边界代表旅程只执行一次");
    await page.route("**/api/generation/analyze", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "REVIEW_REQUIRED",
        analyzedAt: "2026-07-28T00:00:00Z",
        requestDigest: "a".repeat(64),
        request: {
          schema_version: "1.1.0",
          project: {
            name: "inventory-service",
            namespace: "io.elmos.inventory",
            description: "multi entity",
            kind: "api",
            persistence: "postgresql",
            auth_mode: "jwt",
          },
          entities: [
            { singular: "product", plural: "products", fields: [] },
            { singular: "inventory", plural: "inventories", fields: [] },
          ],
          relations: [],
          business_rules: [],
          permissions: [],
          requirements: [],
          acceptance_criteria: [],
          open_questions: [],
          targets: [{ language: "go", framework: "net/http", runtime: "1.25.0", port: 8085 }],
        },
      }),
    }));

    await page.goto("/generation");
    await page.getByLabel("审批者标识").fill("user:e2e");
    await page.getByLabel("租户标识").fill("local-e2e");
    await page.getByLabel("本地 Runner 令牌").fill("elmos-e2e-local-token-32-characters");
    await page.getByLabel("数据配置").selectOption("postgresql");
    await page.locator("label.target-card").filter({ hasText: "Go 1.25.0" })
      .locator('input[type="checkbox"]').check();
    await page.getByRole("button", { name: "锁定生成计划" }).click();
    await page.getByRole("button", { name: "分析并整理需求" }).click();

    await expect(page.getByText(/Go\s*的 PostgreSQL Profile 只接受单实体/)).toBeVisible();
    await expect(page.getByRole("checkbox", { name: /我已审阅结构化需求/ })).toBeDisabled();
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
