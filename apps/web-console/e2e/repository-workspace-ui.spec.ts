import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const workspaceId = "d12ac53a-30b8-4d87-8202-9c9a4b181cf8";
const sourceCommit = "1".repeat(40);
const deliveredCommit = "2".repeat(40);
const originalHash = "a".repeat(64);
const updatedHash = "b".repeat(64);

function workspace(input: {
  hash?: string;
  head?: string;
  pending?: string[];
  pushed?: string | null;
  pullRequestId?: string | null;
  pullRequestUrl?: string | null;
} = {}) {
  const hash = input.hash ?? originalHash;
  return {
    workspaceId,
    provider: "GITEE",
    nativeRepositoryId: "owner/repository",
    requestedRef: "main",
    sourceCommit,
    currentHeadCommit: input.head ?? sourceCommit,
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
    pendingPaths: input.pending ?? [],
    pushedCommit: input.pushed ?? null,
    pullRequestId: input.pullRequestId ?? null,
    pullRequestUrl: input.pullRequestUrl ?? null,
    status: input.pullRequestId
      ? "PULL_REQUEST_CREATED"
      : input.pushed
        ? "PUSHED_VERIFIED"
        : input.pending?.length
          ? "LOCAL_CHANGES_PENDING"
          : (input.head && input.head !== sourceCommit)
            ? "COMMITTED_LOCAL"
            : "READY_FOR_LOCAL_CHANGE",
    externalOperationExecuted: Boolean(input.pushed || input.pullRequestId),
  };
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/telemetry/events", (route) =>
    route.fulfill({ status: 204, body: "" }));
});

test("pulls, reads and locally modifies a Gitee repository without external effects", async ({ page }) => {
  let changed = false;
  let committed = false;
  let pushed = false;
  let pullRequestCreated = false;
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
    if (request.method() === "POST" && url.pathname.endsWith("/commit")) {
      committed = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          workspaceId,
          sourceCommit,
          commitSha: deliveredCommit,
          branch: "elmos/workspace-d12ac53a",
          committedPaths: ["README.md"],
          signed: false,
          status: "COMMITTED_LOCAL",
        }),
      });
      return;
    }
    if (request.method() === "POST" && url.pathname.endsWith("/push")) {
      pushed = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          workspaceId,
          commitSha: deliveredCommit,
          remoteRef: "refs/heads/elmos/workspace-d12ac53a",
          status: "PUSHED_VERIFIED",
          externalOperationExecuted: true,
        }),
      });
      return;
    }
    if (request.method() === "POST" && url.pathname.endsWith("/pull-request")) {
      pullRequestCreated = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          workspaceId,
          providerPullRequestId: "42",
          url: "https://gitee.com/owner/repository/pulls/42",
          status: "PULL_REQUEST_CREATED",
        }),
      });
      return;
    }
    if (request.method() === "GET" && url.pathname.endsWith(workspaceId)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(workspace({
          hash: changed ? updatedHash : originalHash,
          head: committed ? deliveredCommit : sourceCommit,
          pending: changed && !committed ? ["README.md"] : [],
          pushed: pushed ? deliveredCommit : null,
          pullRequestId: pullRequestCreated ? "42" : null,
          pullRequestUrl: pullRequestCreated
            ? "https://gitee.com/owner/repository/pulls/42"
            : null,
        })),
      });
      return;
    }
    await route.fulfill({ status: 404, body: "{}" });
  });

  await page.goto("/repositories");
  await expect(page.getByRole("heading", { name: "代码仓库工作区" })).toBeVisible();
  await page.getByLabel("开发访问令牌").fill("repository-browser-token-32");
  await page.getByLabel("托管平台").selectOption("GITEE");
  await page.getByLabel("HTTPS Clone URL").fill("https://gitee.com/owner/repository.git");
  await page.getByLabel("仓库原生标识").fill("owner/repository");
  await page.getByRole("button", { name: "拉取并建立工作区" }).click();

  await expect(page.getByText("owner/repository", { exact: true })).toBeVisible();
  await expect(page.getByText("交付状态")).toBeVisible();
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

  await expect(page.getByRole("button", { name: "项目生成" })).toBeDisabled();
  await page.getByRole("button", { name: "提交已批准路径" }).click();
  await expect(page.getByText(/已在隔离分支提交/)).toBeVisible();

  page.on("dialog", (dialog) => dialog.accept());
  await page.getByLabel("短期凭据引用").fill("gitee-one-hour-lease");
  await page.getByRole("button", { name: "推送并校验远端" }).click();
  await expect(page.getByText(/远端分支已推送并按提交 SHA 回读校验/)).toBeVisible();
  await page.getByRole("button", { name: "创建 PR" }).click();
  await expect(page.getByRole("link", { name: "打开 PR 42" })).toHaveAttribute(
    "href", "https://gitee.com/owner/repository/pulls/42",
  );

  await page.getByRole("button", { name: "项目生成" }).click();
  await expect(page).toHaveURL(new RegExp(
    `/generation\\?repositoryWorkspaceId=${workspaceId}$`,
  ));
});

test("hands a clean exact-head workspace to translation and Spring", async ({ page }) => {
  await page.route("**/api/repository-workspaces**", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "POST"
      && url.pathname.endsWith("/api/repository-workspaces")) {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(workspace()),
      });
      return;
    }
    await route.fulfill({ status: 404, body: "{}" });
  });
  await page.goto("/repositories");
  await page.getByLabel("开发访问令牌").fill("repository-browser-token-32");
  await page.getByLabel("HTTPS Clone URL").fill("https://gitee.com/owner/repository.git");
  await page.getByLabel("仓库原生标识").fill("owner/repository");
  await page.getByRole("button", { name: "拉取并建立工作区" }).click();

  await page.getByRole("button", { name: "跨语言转换" }).click();
  await expect(page).toHaveURL(
    new RegExp(`/translation\\?repositoryWorkspaceId=${workspaceId}$`),
  );

  await page.goto("/repositories");
  await page.getByLabel("开发访问令牌").fill("repository-browser-token-32");
  await page.getByLabel("HTTPS Clone URL").fill("https://gitee.com/owner/repository.git");
  await page.getByLabel("仓库原生标识").fill("owner/repository");
  await page.getByRole("button", { name: "拉取并建立工作区" }).click();
  await page.getByRole("button", { name: "Spring 现代化" }).click();
  await expect(page).toHaveURL(new RegExp(
    `/spring\\?repositoryWorkspaceId=${workspaceId}&expectedCommitSha=${sourceCommit}&requestedRef=main$`,
  ));
});
