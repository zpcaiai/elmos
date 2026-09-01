"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useAccountSession } from "../components/AccountSessionProvider";
import { Icon } from "../components/Icon";
import styles from "./RepositoryWorkspaceStudio.module.css";

type Provider = "GITHUB" | "GITEE" | "GENERIC_GIT";
type FileCategory =
  | "SOURCE"
  | "DOCUMENTATION"
  | "CONFIGURATION"
  | "LOCAL_DEPLOYMENT"
  | "CLOUD_DEPLOYMENT"
  | "TEST"
  | "OTHER";

type FileEntry = {
  path: string;
  bytes: number;
  sha256: string;
  category: FileCategory;
  readable: boolean;
  writable: boolean;
};

type Workspace = {
  workspaceId: string;
  provider: Provider;
  nativeRepositoryId: string;
  requestedRef: string;
  sourceCommit: string;
  currentHeadCommit: string;
  branch: string;
  completeness: "COMPLETE" | "INCOMPLETE_SUBMODULES" | "INCOMPLETE_LFS";
  codeOwnersPresent: boolean;
  blockers: string[];
  files: FileEntry[];
  pendingPaths: string[];
  pushedCommit?: string | null;
  pullRequestId?: string | null;
  pullRequestUrl?: string | null;
  status: string;
  externalOperationExecuted: boolean;
};

type WorkspaceResponse = Omit<Workspace, "currentHeadCommit" | "pendingPaths"> & {
  currentHeadCommit?: string | null;
  pendingPaths?: string[] | null;
};

type FileContent = {
  path: string;
  sha256: string;
  category: FileCategory;
  encoding: "UTF-8";
  content: string;
};

type ApiError = { errorCode?: string; message?: string; retryable?: boolean };

const categoryLabels: Record<FileCategory, string> = {
  SOURCE: "源代码",
  DOCUMENTATION: "说明文档",
  CONFIGURATION: "配置文件",
  LOCAL_DEPLOYMENT: "本地部署",
  CLOUD_DEPLOYMENT: "云端部署",
  TEST: "测试",
  OTHER: "其他",
};
const workspaceStorageKey = "elmos:repository-workspace-id:v1";
const workspaceIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function base64Utf8(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function normalizeWorkspace(response: WorkspaceResponse): Workspace {
  return {
    ...response,
    // Responses created before controlled delivery was introduced did not
    // carry these fields. Such a workspace is still at its immutable source
    // commit and has no server-reported local changes.
    currentHeadCommit: response.currentHeadCommit || response.sourceCommit,
    pendingPaths: Array.isArray(response.pendingPaths) ? response.pendingPaths : [],
  };
}

export function RepositoryWorkspaceStudio() {
  const account = useAccountSession();
  const [accessToken, setAccessToken] = useState("");
  const [provider, setProvider] = useState<Provider>("GITHUB");
  const [cloneUrl, setCloneUrl] = useState("https://github.com/");
  const [requestedRef, setRequestedRef] = useState("main");
  const [nativeRepositoryId, setNativeRepositoryId] = useState("");
  const [providerInstanceId, setProviderInstanceId] = useState("github.com");
  const [credentialRef, setCredentialRef] = useState("");
  const [recoveryId, setRecoveryId] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selected, setSelected] = useState<FileContent | null>(null);
  const [editor, setEditor] = useState("");
  const [intent, setIntent] = useState("实现用户确认的功能修改，并保留现有行为与部署安全边界。");
  const [ownerApproved, setOwnerApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [filter, setFilter] = useState<FileCategory | "ALL">("ALL");
  const [newPath, setNewPath] = useState("");
  const [commitMessage, setCommitMessage] = useState("Implement the approved ELMOS workspace changes");
  const [deliveryCredentialRef, setDeliveryCredentialRef] = useState("");
  const [baseBranch, setBaseBranch] = useState("main");
  const [pullRequestTitle, setPullRequestTitle] = useState("ELMOS: implement approved changes");
  const [pullRequestBody, setPullRequestBody] = useState(
    "This pull request was prepared from a tenant-bound ELMOS workspace. Merge and deployment remain separate reviewed actions.",
  );
  const [pullRequestKey, setPullRequestKey] = useState(() => crypto.randomUUID());

  const files = useMemo(
    () => (workspace?.files ?? []).filter((file) => filter === "ALL" || file.category === filter),
    [workspace?.files, filter],
  );

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(workspaceStorageKey) ?? "";
      if (workspaceIdPattern.test(stored)) setRecoveryId(stored);
    } catch {
      // Recovery remains available through explicit UUID entry.
    }
  }, []);

  function authorization(): HeadersInit {
    return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
  }

  async function jsonRequest<T>(url: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(url, {
      ...init,
      cache: "no-store",
      headers: {
        ...authorization(),
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
    const payload = await response.json() as T & ApiError;
    if (!response.ok) {
      throw new Error(payload.message || payload.errorCode || `HTTP_${response.status}`);
    }
    return payload;
  }

  function changeProvider(next: Provider) {
    setProvider(next);
    if (next === "GITHUB") {
      setProviderInstanceId("github.com");
      setCloneUrl("https://github.com/");
    } else if (next === "GITEE") {
      setProviderInstanceId("gitee.com");
      setCloneUrl("https://gitee.com/");
    } else {
      setProviderInstanceId("self-hosted");
      setCloneUrl("https://");
    }
  }

  async function createWorkspace(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFeedback("");
    try {
      const created = normalizeWorkspace(
        await jsonRequest<WorkspaceResponse>("/api/repository-workspaces", {
          method: "POST",
          body: JSON.stringify({
            provider,
            providerInstanceId,
            nativeRepositoryId,
            cloneUrl,
            requestedRef,
            credentialRef: credentialRef || null,
          }),
        }),
      );
      setWorkspace(created);
      setRecoveryId(created.workspaceId);
      try { sessionStorage.setItem(workspaceStorageKey, created.workspaceId); } catch { /* optional */ }
      setSelected(null);
      setEditor("");
      setFeedback(created.completeness === "COMPLETE"
        ? "已按精确提交创建隔离工作区，可读取并审阅本地修改。"
        : "仓库已拉取，但子模块或 LFS 对象尚未独立授权与校验，因此保持只读。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "仓库工作区创建失败。");
    } finally {
      setBusy(false);
    }
  }

  async function refreshWorkspace(): Promise<Workspace> {
    if (!workspace) throw new Error("请先建立工作区。");
    const refreshed = normalizeWorkspace(
      await jsonRequest<WorkspaceResponse>(
        `/api/repository-workspaces/${workspace.workspaceId}`,
      ),
    );
    setWorkspace(refreshed);
    return refreshed;
  }

  async function commitWorkspace() {
    if (!workspace || workspace.pendingPaths.length === 0) return;
    setBusy(true);
    setFeedback("");
    try {
      const result = await jsonRequest<{ commitSha: string; committedPaths: string[] }>(
        `/api/repository-workspaces/${workspace.workspaceId}/commit`,
        {
          method: "POST",
          body: JSON.stringify({
            expectedHeadCommit: workspace.currentHeadCommit,
            message: commitMessage,
            codeOwnerApproval: ownerApproved,
            approvedPaths: workspace.pendingPaths,
          }),
        },
      );
      await refreshWorkspace();
      setFeedback(`已在隔离分支提交 ${result.commitSha.slice(0, 12)}；尚未推送。`);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "本地提交失败。");
    } finally {
      setBusy(false);
    }
  }

  async function pushWorkspace() {
    if (!workspace || workspace.pendingPaths.length > 0
      || !window.confirm(`将 ${workspace.branch} 推送到远端仓库？不会强推、合并或部署。`)) return;
    setBusy(true);
    setFeedback("");
    try {
      await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}/push`, {
        method: "POST",
        body: JSON.stringify({
          expectedCommit: workspace.currentHeadCommit,
          credentialRef: deliveryCredentialRef || null,
        }),
      });
      await refreshWorkspace();
      setFeedback("远端分支已推送并按提交 SHA 回读校验；尚未创建 PR、合并或部署。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "远端推送失败。");
    } finally {
      setBusy(false);
    }
  }

  async function createPullRequest() {
    if (!workspace || workspace.pushedCommit !== workspace.currentHeadCommit
      || !window.confirm(`将在 ${workspace.provider} 创建面向 ${baseBranch} 的 PR。继续？`)) return;
    setBusy(true);
    setFeedback("");
    try {
      const result = await jsonRequest<{ providerPullRequestId: string; url: string; status: string }>(
        `/api/repository-workspaces/${workspace.workspaceId}/pull-request`,
        {
          method: "POST",
          body: JSON.stringify({
            expectedCommit: workspace.currentHeadCommit,
            baseBranch,
            title: pullRequestTitle,
            body: pullRequestBody,
            idempotencyKey: pullRequestKey,
            credentialRef: deliveryCredentialRef || null,
          }),
        },
      );
      await refreshWorkspace();
      setFeedback(`PR ${result.providerPullRequestId} 已创建；合并和部署仍需独立审批。`);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "PR 创建失败。");
    } finally {
      setBusy(false);
    }
  }

  async function recoverWorkspace() {
    if (!recoveryId) return;
    setBusy(true);
    setFeedback("");
    try {
      const recovered = normalizeWorkspace(
        await jsonRequest<WorkspaceResponse>(
          `/api/repository-workspaces/${recoveryId}`,
        ),
      );
      setWorkspace(recovered);
      try { sessionStorage.setItem(workspaceStorageKey, recovered.workspaceId); } catch { /* optional */ }
      setSelected(null);
      setEditor("");
      setFeedback("已按当前租户与操作者身份恢复隔离工作区。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "工作区恢复失败。");
    } finally {
      setBusy(false);
    }
  }

  async function openFile(file: FileEntry) {
    if (!workspace) return;
    setBusy(true);
    setFeedback("");
    try {
      const content = await jsonRequest<FileContent>(
        `/api/repository-workspaces/${workspace.workspaceId}/files?${new URLSearchParams({ path: file.path })}`,
      );
      setSelected(content);
      setEditor(content.content);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "文件读取失败。");
    } finally {
      setBusy(false);
    }
  }

  async function applyChange() {
    if (!workspace || !selected) return;
    setBusy(true);
    setFeedback("");
    try {
      await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}/changes`, {
        method: "POST",
        body: JSON.stringify({
          baseCommit: workspace.sourceCommit,
          intent,
          codeOwnerApproval: ownerApproved,
          approvedPaths: [selected.path],
          changes: [{
            operation: "UPSERT",
            path: selected.path,
            expectedSha256: selected.sha256 || null,
            contentBase64: base64Utf8(editor),
          }],
        }),
      });
      const refreshed = normalizeWorkspace(
        await jsonRequest<WorkspaceResponse>(
          `/api/repository-workspaces/${workspace.workspaceId}`,
        ),
      );
      const content = await jsonRequest<FileContent>(
        `/api/repository-workspaces/${workspace.workspaceId}/files?${new URLSearchParams({ path: selected.path })}`,
      );
      setWorkspace(refreshed);
      setSelected(content);
      setEditor(content.content);
      setFeedback("修改已写入隔离工作区，尚未推送、创建 PR、合并或部署。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "文件修改失败。");
    } finally {
      setBusy(false);
    }
  }

  function beginNewFile() {
    const path = newPath.trim();
    if (!path || path.startsWith("/") || path.split("/").includes("..") || path.includes("\\")) {
      setFeedback("请输入仓库内的安全相对路径。");
      return;
    }
    if (workspace?.files.some((file) => file.path === path)) {
      setFeedback("该文件已经存在，请从文件列表中打开。");
      return;
    }
    setSelected({
      path,
      sha256: "",
      category: "OTHER",
      encoding: "UTF-8",
      content: "",
    });
    setEditor("");
    setFeedback("新文件尚未写入；填写内容并保存后才会进入隔离工作区。");
  }

  async function deleteSelectedFile() {
    if (!workspace || !selected?.sha256
      || !window.confirm(`删除 ${selected.path}？该操作只影响隔离工作区。`)) return;
    setBusy(true);
    setFeedback("");
    try {
      await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}/changes`, {
        method: "POST",
        body: JSON.stringify({
          baseCommit: workspace.sourceCommit,
          intent,
          codeOwnerApproval: ownerApproved,
          approvedPaths: [selected.path],
          changes: [{
            operation: "DELETE",
            path: selected.path,
            expectedSha256: selected.sha256,
            contentBase64: null,
          }],
        }),
      });
      const refreshed = normalizeWorkspace(
        await jsonRequest<WorkspaceResponse>(
          `/api/repository-workspaces/${workspace.workspaceId}`,
        ),
      );
      setWorkspace(refreshed);
      setSelected(null);
      setEditor("");
      setFeedback("文件已从隔离工作区删除；远端仓库未发生变化。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "文件删除失败。");
    } finally {
      setBusy(false);
    }
  }

  async function deleteWorkspace() {
    if (!workspace || !window.confirm("删除此隔离工作区？未推送的本地修改将被移除。")) return;
    setBusy(true);
    setFeedback("");
    try {
      await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}`, { method: "DELETE" });
      setWorkspace(null);
      setSelected(null);
      setEditor("");
      try { sessionStorage.removeItem(workspaceStorageKey); } catch { /* optional */ }
      setFeedback("隔离工作区已删除；远端仓库未发生任何变化。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "工作区删除失败。");
    } finally {
      setBusy(false);
    }
  }

  function continueToProjectGeneration() {
    if (!workspace || workspace.completeness !== "COMPLETE") return;
    const search = new URLSearchParams({ repositoryWorkspaceId: workspace.workspaceId });
    window.location.assign(`/generation?${search}`);
  }

  function continueToTranslation() {
    if (!workspace || workspace.completeness !== "COMPLETE"
      || workspace.pendingPaths.length > 0) return;
    const search = new URLSearchParams({ repositoryWorkspaceId: workspace.workspaceId });
    window.location.assign(`/translation?${search}`);
  }

  function continueToSpring() {
    if (!workspace || workspace.completeness !== "COMPLETE"
      || workspace.pendingPaths.length > 0) return;
    const search = new URLSearchParams({
      repositoryWorkspaceId: workspace.workspaceId,
      expectedCommitSha: workspace.currentHeadCommit,
      requestedRef: workspace.requestedRef,
    });
    window.location.assign(`/spring?${search}`);
  }

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>Repository workspace</span>
          <h1>代码仓库工作区</h1>
          <p>从 GitHub、Gitee 或其他 HTTPS Git 服务拉取精确提交，读取并修改代码、说明、配置以及本地/云端部署文件，并交接到完整项目生成流程。</p>
        </div>
        <div className={styles.boundary}>
          <Icon name="lock" size={18} />
          <div><strong>受控交付边界</strong><small>Commit、Push、PR 分权执行；不自动合并或部署</small></div>
        </div>
      </section>

      <form className={styles.connect} onSubmit={createWorkspace}>
        {account.status !== "authenticated" && <label className={styles.tokenField}>开发访问令牌
          <input type="password" autoComplete="off" value={accessToken}
            onChange={(event) => setAccessToken(event.target.value)}
            placeholder="仅保存在当前页面内存中" required minLength={24} />
        </label>}
        {account.status === "authenticated" && <div className={styles.accountIdentity}>
          <span>当前企业身份</span>
          <strong>{account.principal?.displayName}</strong>
          <small>{account.principal?.organizationId}</small>
        </div>}
        <label>托管平台
          <select value={provider} onChange={(event) => changeProvider(event.target.value as Provider)}>
            <option value="GITHUB">GitHub</option>
            <option value="GITEE">Gitee</option>
            <option value="GENERIC_GIT">其他 Git</option>
          </select>
        </label>
        <label className={styles.urlField}>HTTPS Clone URL
          <input value={cloneUrl} onChange={(event) => setCloneUrl(event.target.value)}
            placeholder="https://host/owner/repository.git" required />
        </label>
        <label>分支 / 标签 / 提交
          <input value={requestedRef} onChange={(event) => setRequestedRef(event.target.value)} required />
        </label>
        <label>仓库原生标识
          <input value={nativeRepositoryId} onChange={(event) => setNativeRepositoryId(event.target.value)}
            placeholder="owner/repository" required />
        </label>
        <label>Provider 实例
          <input value={providerInstanceId} onChange={(event) => setProviderInstanceId(event.target.value)} required />
        </label>
        <label>私库凭据引用（可选）
          <input value={credentialRef} onChange={(event) => setCredentialRef(event.target.value)}
            placeholder="server-side credential ref" />
        </label>
        <button className={styles.primary} type="submit" disabled={busy}>拉取并建立工作区</button>
        <label className={styles.recoveryField}>恢复工作区 ID
          <input value={recoveryId} onChange={(event) => setRecoveryId(event.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
        </label>
        <button className={styles.secondary} type="button" onClick={recoverWorkspace}
          disabled={busy || !recoveryId}>按身份恢复</button>
      </form>

      {feedback && <div className={styles.feedback} role="status">{feedback}</div>}

      {workspace && <>
        <section className={styles.metrics} aria-label="工作区状态">
          <article><span>当前 HEAD</span><strong>{workspace.currentHeadCommit.slice(0, 12)}</strong><small>来源 {workspace.sourceCommit.slice(0, 12)} · {workspace.requestedRef}</small></article>
          <article><span>文件总数</span><strong>{workspace.files.length}</strong><small>最多受服务端限额约束</small></article>
          <article><span>完整性</span><strong>{workspace.completeness === "COMPLETE" ? "完整" : "只读"}</strong><small>{workspace.blockers.join(" · ") || "无阻断项"}</small></article>
          <article><span>交付状态</span><strong>{workspace.status}</strong><small>{workspace.pullRequestId ? `PR ${workspace.pullRequestId}` : workspace.pushedCommit ? "远端分支已校验" : "远端未变更"}</small></article>
        </section>

        <div className={styles.toolbar}>
          <div><strong>{workspace.nativeRepositoryId}</strong><small>{workspace.workspaceId} · {workspace.branch}</small></div>
          <label>新文件路径
            <input value={newPath} onChange={(event) => setNewPath(event.target.value)}
              placeholder="docs/new-file.md" />
          </label>
          <button className={styles.secondary} type="button" onClick={beginNewFile}
            disabled={busy || workspace.completeness !== "COMPLETE"}>新建文件</button>
          <button className={styles.primary} type="button" onClick={continueToProjectGeneration}
            disabled={busy || workspace.completeness !== "COMPLETE"
              || workspace.pendingPaths.length > 0}>
            项目生成
          </button>
          <button className={styles.secondary} type="button" onClick={continueToTranslation}
            disabled={busy || workspace.completeness !== "COMPLETE"
              || workspace.pendingPaths.length > 0}>
            跨语言转换
          </button>
          <button className={styles.secondary} type="button" onClick={continueToSpring}
            disabled={busy || workspace.completeness !== "COMPLETE"
              || workspace.pendingPaths.length > 0}>
            Spring 现代化
          </button>
          <label>文件分类
            <select value={filter} onChange={(event) => setFilter(event.target.value as FileCategory | "ALL")}>
              <option value="ALL">全部</option>
              {Object.entries(categoryLabels).map(([value, label]) =>
                <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          <button className={styles.danger} type="button" onClick={deleteWorkspace} disabled={busy}>删除本地工作区</button>
        </div>

        <section className={styles.workspaceGrid}>
          <div className={styles.filePanel}>
            <header><h2>仓库文件</h2><small>{files.length} 项</small></header>
            <div className={styles.fileList}>
              {files.map((file) => <button type="button" key={file.path}
                className={selected?.path === file.path ? styles.activeFile : ""}
                onClick={() => openFile(file)} disabled={busy || !file.readable}>
                <span><strong>{file.path}</strong><small>{categoryLabels[file.category]} · {file.bytes} B</small></span>
                <em>{!file.readable ? "受保护" : file.writable ? "可修改" : "只读"}</em>
              </button>)}
            </div>
          </div>

          <div className={styles.editorPanel}>
            {selected ? <>
              <header><div><h2>{selected.path}</h2><small>UTF-8 · {selected.sha256.slice(0, 16)}…</small></div>
                <span>{categoryLabels[selected.category]}</span></header>
              <textarea aria-label="文件内容" spellCheck={false} value={editor}
                onChange={(event) => setEditor(event.target.value)} disabled={
                  workspace.completeness !== "COMPLETE"
                  || workspace.files.find((file) => file.path === selected.path)?.readable === false
                  || workspace.files.find((file) => file.path === selected.path)?.writable === false
                } />
              <label className={styles.intent}>变更意图
                <textarea value={intent} onChange={(event) => setIntent(event.target.value)} maxLength={2000} />
              </label>
              {workspace.codeOwnersPresent && <label className={styles.approval}>
                <input type="checkbox" checked={ownerApproved}
                  onChange={(event) => setOwnerApproved(event.target.checked)} />
                已获得此路径所需的 CODEOWNERS 明确批准
              </label>}
              <div className={styles.editorActions}>
                <span>保存只写入隔离工作区，不触发外部操作。</span>
                <div>
                  <button className={styles.danger} type="button" onClick={deleteSelectedFile}
                    disabled={busy || !selected.sha256 || workspace.completeness !== "COMPLETE"}>
                    删除文件
                  </button>
                  <button className={styles.primary} type="button" onClick={applyChange}
                    disabled={busy
                      || (selected.sha256 !== "" && editor === selected.content)
                      || workspace.completeness !== "COMPLETE"}>
                    保存本地修改
                  </button>
                </div>
              </div>
            </> : <div className={styles.empty}><Icon name="file" size={26} /><strong>选择一个文本文件</strong><span>二进制、密钥与受保护路径不会开放编辑。</span></div>}
          </div>
        </section>

        <section className={styles.delivery} aria-label="受控代码交付">
          <header>
            <div><span className={styles.eyebrow}>Controlled delivery</span><h2>提交、推送与 Pull Request</h2></div>
            <small>每一步都校验租户、权限、HEAD 和路径范围；不会自动合并或部署。</small>
          </header>
          <div className={styles.deliveryGrid}>
            <article>
              <strong>1. 本地 Commit</strong>
              <label>提交说明<input value={commitMessage} maxLength={4000}
                onChange={(event) => setCommitMessage(event.target.value)} /></label>
              <small>{workspace.pendingPaths.length > 0
                ? `${workspace.pendingPaths.length} 个待提交路径：${workspace.pendingPaths.join("、")}`
                : "没有待提交文件。"}</small>
              <button className={styles.primary} type="button" onClick={commitWorkspace}
                data-operation-id="repository.commit"
                disabled={busy || workspace.pendingPaths.length === 0 || commitMessage.trim().length === 0}>
                提交已批准路径
              </button>
            </article>
            <article>
              <strong>2. 推送受控分支</strong>
              <label>短期凭据引用<input value={deliveryCredentialRef}
                onChange={(event) => setDeliveryCredentialRef(event.target.value)}
                placeholder="最长 1 小时的服务端 Lease" /></label>
              <small>仅推送 {workspace.branch}；禁止 force push，并回读远端 SHA。</small>
              <button className={styles.primary} type="button" onClick={pushWorkspace}
                data-operation-id="repository.push"
                disabled={busy || workspace.pendingPaths.length > 0
                  || workspace.currentHeadCommit === workspace.sourceCommit
                  || workspace.pushedCommit === workspace.currentHeadCommit}>
                推送并校验远端
              </button>
            </article>
            <article>
              <strong>3. 创建 Pull Request</strong>
              <label>目标分支<input value={baseBranch}
                onChange={(event) => setBaseBranch(event.target.value)} /></label>
              <label>标题<input value={pullRequestTitle} maxLength={240}
                onChange={(event) => setPullRequestTitle(event.target.value)} /></label>
              <label>说明<textarea value={pullRequestBody} maxLength={8000}
                onChange={(event) => setPullRequestBody(event.target.value)} /></label>
              <button className={styles.primary} type="button" onClick={createPullRequest}
                data-operation-id="repository.pull_request"
                disabled={busy || provider === "GENERIC_GIT"
                  || workspace.pushedCommit !== workspace.currentHeadCommit
                  || Boolean(workspace.pullRequestId)}>
                创建 PR
              </button>
              {workspace.pullRequestUrl && <a href={workspace.pullRequestUrl}
                target="_blank" rel="noreferrer">打开 PR {workspace.pullRequestId}</a>}
            </article>
          </div>
          <input type="hidden" value={pullRequestKey}
            onChange={(event) => setPullRequestKey(event.target.value)} />
        </section>
      </>}
    </div>
  );
}
