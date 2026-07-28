import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const workspaceId = "d12ac53a-30b8-4d87-8202-9c9a4b181cf8";
const sourceCommit = "1".repeat(40);
const originalHash = "a".repeat(64);
const updatedHash = "b".repeat(64);

function workspace(hash = originalHash) {
  return {
    workspaceId,
    provider: "GITEE",
    nativeRepositoryId: "owner/repository",
    requestedRef: "main",
    sourceCommit,
    branch: "elmos/workspace-d12ac53a",
    completeness: "COMPLETE",
    codeOwnersPresent: true,
    blockers: [],
    files: [
      {
        path: "README.md",
        bytes: 9,
        sha256: hash,
        category: "DOCUMENTATION",
        writable: true,
      },
      {
        path: ".github/workflows/deploy.yml",
        bytes: 12,
        sha256: "c".repeat(64),
        category: "CLOUD_DEPLOYMENT",
        writable: true,
      },
    ],
    status: "READY_FOR_LOCAL_CHANGE",
    externalOperationExecuted: false,
  };
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 204, body: "" }));
});

test("pulls, reads and locally modifies a Gitee repository without external effects", async ({ page }) => {
  let changed = false;
  let observedChange: Record<string, unknown> | null = null;
  await page.route("**/api/repository-workspaces**", async (route) => {
    const request = route.request();
    expect(request.headers().authorization).toBe("Bearer repository-browser-token-32");
    const url = new URL(request.url());
    if (request.method() === "POST" && url.pathname.endsWith("/api/repository-workspaces")) {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(workspace()),
      });
      return;
    }
    if (request.method() === "GET" && url.pathname.endsWith("/files")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          workspaceId,
          path: "README.md",
          sha256: changed ? updatedHash : originalHash,
          category: "DOCUMENTATION",
          encoding: "UTF-8",
          content: changed ? "# After\n" : "# Before\n",
        }),
      });
      return;
    }
    if (request.method() === "POST" && url.pathname.endsWith("/changes")) {
      observedChange = request.postDataJSON() as Record<string, unknown>;
      changed = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          workspaceId,
          sourceCommit,
          branch: "elmos/workspace-d12ac53a",
          changedPaths: ["README.md"],
          deletedPaths: [],
          untrackedPaths: [],
          status: "LOCAL_CHANGES_READY_FOR_REVIEW",
          pushed: false,
          pullRequestCreated: false,
          deployed: false,
        }),
      });
      return;
    }
    if (request.method() === "GET" && url.pathname.endsWith(workspaceId)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(workspace(updatedHash)),
      });
      return;
    }
    await route.fulfill({ status: 404, body: "{}" });
  });

  await page.goto("/repositories");
  await expect(page.getByRole("heading", { name: "代码仓库工作区" })).toBeVisible();
  await page.getByLabel("访问令牌").fill("repository-browser-token-32");
  await page.getByLabel("托管平台").selectOption("GITEE");
  await page.getByLabel("HTTPS Clone URL").fill("https://gitee.com/owner/repository.git");
  await page.getByLabel("仓库原生标识").fill("owner/repository");
  await page.getByRole("button", { name: "拉取并建立工作区" }).click();

  await expect(page.getByText("owner/repository", { exact: true })).toBeVisible();
  await expect(page.getByText("远端副作用")).toBeVisible();
  await page.getByRole("button", { name: /README\.md/ }).click();
  await page.getByLabel("文件内容").fill("# After\n");
  await page.getByRole("checkbox", { name: /CODEOWNERS/ }).check();
  await page.getByRole("button", { name: "保存本地修改" }).click();

  await expect(page.getByText("尚未推送、创建 PR、合并或部署")).toBeVisible();
  expect(observedChange).toMatchObject({
    baseCommit: sourceCommit,
    codeOwnerApproval: true,
    approvedPaths: ["README.md"],
    changes: [{
      operation: "UPSERT",
      path: "README.md",
      expectedSha256: originalHash,
    }],
  });
  expect(JSON.stringify(observedChange)).toContain("IyBBZnRlcgo=");

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});
