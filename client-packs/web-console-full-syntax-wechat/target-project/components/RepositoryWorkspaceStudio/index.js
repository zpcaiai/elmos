// Top-level helpers and constants
try { var categoryLabels = {
    SOURCE: "源代码",
    DOCUMENTATION: "说明文档",
    CONFIGURATION: "配置文件",
    LOCAL_DEPLOYMENT: "本地部署",
    CLOUD_DEPLOYMENT: "云端部署",
    TEST: "测试",
    OTHER: "其他",
}; } catch(e) {}
try { var workspaceStorageKey = "elmos:repository-workspace-id:v1"; } catch(e) {}
try { var workspaceIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i; } catch(e) {}
try { var base64Utf8 = function base64Utf8(value) {
    const bytes = new TextEncoder().encode(value);
    let binary = "";
    for (const byte of bytes)
        binary += String.fromCharCode(byte);
    return btoa(binary);
} } catch(e) {}
try { var normalizeWorkspace = function normalizeWorkspace(response) {
    return {
        ...response,
        // Responses created before controlled delivery was introduced did not
        // carry these fields. Such a workspace is still at its immutable source
        // commit and has no server-reported local changes.
        currentHeadCommit: response.currentHeadCommit || response.sourceCommit,
        pendingPaths: Array.isArray(response.pendingPaths) ? response.pendingPaths : [],
    };
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    accessToken: "",
    provider: "GITHUB",
    cloneUrl: "https://github.com/",
    requestedRef: "main",
    nativeRepositoryId: "",
    providerInstanceId: "github.com",
    credentialRef: "",
    recoveryId: "",
    workspace: null,
    selected: null,
    editor: "",
    intent: "实现用户确认的功能修改，并保留现有行为与部署安全边界。",
    ownerApproved: false,
    busy: false,
    feedback: "",
    filter: "ALL",
    newPath: "",
    commitMessage: "Implement the approved ELMOS workspace changes",
    deliveryCredentialRef: "",
    baseBranch: "main",
    pullRequestTitle: "ELMOS: implement approved changes",
    pullRequestBody: "This pull request was prepared from a tenant-bound ELMOS workspace. Merge and deployment remain separate reviewed actions.",
    pullRequestKey: null,
    files: null,
  },
  lifetimes: {
    attached() {
      const setAccessToken = (val) => { this.setData({ accessToken: typeof val === "function" ? val(this.data.accessToken) : val }); };
      const setProvider = (val) => { this.setData({ provider: typeof val === "function" ? val(this.data.provider) : val }); };
      const setCloneUrl = (val) => { this.setData({ cloneUrl: typeof val === "function" ? val(this.data.cloneUrl) : val }); };
      const setRequestedRef = (val) => { this.setData({ requestedRef: typeof val === "function" ? val(this.data.requestedRef) : val }); };
      const setNativeRepositoryId = (val) => { this.setData({ nativeRepositoryId: typeof val === "function" ? val(this.data.nativeRepositoryId) : val }); };
      const setProviderInstanceId = (val) => { this.setData({ providerInstanceId: typeof val === "function" ? val(this.data.providerInstanceId) : val }); };
      const setCredentialRef = (val) => { this.setData({ credentialRef: typeof val === "function" ? val(this.data.credentialRef) : val }); };
      const setRecoveryId = (val) => { this.setData({ recoveryId: typeof val === "function" ? val(this.data.recoveryId) : val }); };
      const setWorkspace = (val) => { this.setData({ workspace: typeof val === "function" ? val(this.data.workspace) : val }); };
      const setSelected = (val) => { this.setData({ selected: typeof val === "function" ? val(this.data.selected) : val }); };
      const setEditor = (val) => { this.setData({ editor: typeof val === "function" ? val(this.data.editor) : val }); };
      const setIntent = (val) => { this.setData({ intent: typeof val === "function" ? val(this.data.intent) : val }); };
      const setOwnerApproved = (val) => { this.setData({ ownerApproved: typeof val === "function" ? val(this.data.ownerApproved) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
      const setFeedback = (val) => { this.setData({ feedback: typeof val === "function" ? val(this.data.feedback) : val }); };
      const setFilter = (val) => { this.setData({ filter: typeof val === "function" ? val(this.data.filter) : val }); };
      const setNewPath = (val) => { this.setData({ newPath: typeof val === "function" ? val(this.data.newPath) : val }); };
      const setCommitMessage = (val) => { this.setData({ commitMessage: typeof val === "function" ? val(this.data.commitMessage) : val }); };
      const setDeliveryCredentialRef = (val) => { this.setData({ deliveryCredentialRef: typeof val === "function" ? val(this.data.deliveryCredentialRef) : val }); };
      const setBaseBranch = (val) => { this.setData({ baseBranch: typeof val === "function" ? val(this.data.baseBranch) : val }); };
      const setPullRequestTitle = (val) => { this.setData({ pullRequestTitle: typeof val === "function" ? val(this.data.pullRequestTitle) : val }); };
      const setPullRequestBody = (val) => { this.setData({ pullRequestBody: typeof val === "function" ? val(this.data.pullRequestBody) : val }); };
      const setPullRequestKey = (val) => { this.setData({ pullRequestKey: typeof val === "function" ? val(this.data.pullRequestKey) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          try {
        const stored = sessionStorage.getItem(workspaceStorageKey) ?? "";
        if (workspaceIdPattern.test(stored))
            setRecoveryId(stored);
    }
    catch {
        // Recovery remains available through explicit UUID entry.
    }
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    authorization() {
      try {
        return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
      } catch (err) {
        console.warn("authorization execution warning:", err);
      }
    },
    async jsonRequest(url, init) {
      try {
        const response = await fetch(url, {
        ...init,
        cache: "no-store",
        headers: {
            ...authorization(),
            ...(init.body ? { "Content-Type": "application/json" } : {}),
            ...init.headers,
        },
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.message || payload.errorCode || `HTTP_${response.status}`);
    }
    return payload;
      } catch (err) {
        console.warn("jsonRequest execution warning:", err);
      }
    },
    changeProvider(next) {
      try {
        setProvider(next);
    if (next === "GITHUB") {
        setProviderInstanceId("github.com");
        setCloneUrl("https://github.com/");
    }
    else if (next === "GITEE") {
        setProviderInstanceId("gitee.com");
        setCloneUrl("https://gitee.com/");
    }
    else {
        setProviderInstanceId("self-hosted");
        setCloneUrl("https://");
    }
      } catch (err) {
        console.warn("changeProvider execution warning:", err);
      }
    },
    async createWorkspace(event) {
      try {
        event.preventDefault();
    setBusy(true);
    setFeedback("");
    try {
        const created = normalizeWorkspace(await jsonRequest("/api/repository-workspaces", {
            method: "POST",
            body: JSON.stringify({
                provider,
                providerInstanceId,
                nativeRepositoryId,
                cloneUrl,
                requestedRef,
                credentialRef: credentialRef || null,
            }),
        }));
        setWorkspace(created);
        setRecoveryId(created.workspaceId);
        try {
            sessionStorage.setItem(workspaceStorageKey, created.workspaceId);
        }
        catch { /* optional */ }
        setSelected(null);
        setEditor("");
        setFeedback(created.completeness === "COMPLETE"
            ? "已按精确提交创建隔离工作区，可读取并审阅本地修改。"
            : "仓库已拉取，但子模块或 LFS 对象尚未独立授权与校验，因此保持只读。");
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "仓库工作区创建失败。");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("createWorkspace execution warning:", err);
      }
    },
    async refreshWorkspace() {
      try {
        if (!workspace)
        throw new Error("请先建立工作区。");
    const refreshed = normalizeWorkspace(await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}`));
    setWorkspace(refreshed);
    return refreshed;
      } catch (err) {
        console.warn("refreshWorkspace execution warning:", err);
      }
    },
    async commitWorkspace() {
      try {
        if (!workspace || workspace.pendingPaths.length === 0)
        return;
    setBusy(true);
    setFeedback("");
    try {
        const result = await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}/commit`, {
            method: "POST",
            body: JSON.stringify({
                expectedHeadCommit: workspace.currentHeadCommit,
                message: commitMessage,
                codeOwnerApproval: ownerApproved,
                approvedPaths: workspace.pendingPaths,
            }),
        });
        await refreshWorkspace();
        setFeedback(`已在隔离分支提交 ${result.commitSha.slice(0, 12)}；尚未推送。`);
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "本地提交失败。");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("commitWorkspace execution warning:", err);
      }
    },
    async pushWorkspace() {
      try {
        if (!workspace || workspace.pendingPaths.length > 0
        || !window.confirm(`将 ${workspace.branch} 推送到远端仓库？不会强推、合并或部署。`))
        return;
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
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "远端推送失败。");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("pushWorkspace execution warning:", err);
      }
    },
    async createPullRequest() {
      try {
        if (!workspace || workspace.pushedCommit !== workspace.currentHeadCommit
        || !window.confirm(`将在 ${workspace.provider} 创建面向 ${baseBranch} 的 PR。继续？`))
        return;
    setBusy(true);
    setFeedback("");
    try {
        const result = await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}/pull-request`, {
            method: "POST",
            body: JSON.stringify({
                expectedCommit: workspace.currentHeadCommit,
                baseBranch,
                title: pullRequestTitle,
                body: pullRequestBody,
                idempotencyKey: pullRequestKey,
                credentialRef: deliveryCredentialRef || null,
            }),
        });
        await refreshWorkspace();
        setFeedback(`PR ${result.providerPullRequestId} 已创建；合并和部署仍需独立审批。`);
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "PR 创建失败。");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("createPullRequest execution warning:", err);
      }
    },
    async recoverWorkspace() {
      try {
        if (!recoveryId)
        return;
    setBusy(true);
    setFeedback("");
    try {
        const recovered = normalizeWorkspace(await jsonRequest(`/api/repository-workspaces/${recoveryId}`));
        setWorkspace(recovered);
        try {
            sessionStorage.setItem(workspaceStorageKey, recovered.workspaceId);
        }
        catch { /* optional */ }
        setSelected(null);
        setEditor("");
        setFeedback("已按当前租户与操作者身份恢复隔离工作区。");
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "工作区恢复失败。");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("recoverWorkspace execution warning:", err);
      }
    },
    async openFile(file) {
      try {
        if (!workspace)
        return;
    setBusy(true);
    setFeedback("");
    try {
        const content = await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}/files?${new URLSearchParams({ path: file.path })}`);
        setSelected(content);
        setEditor(content.content);
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "文件读取失败。");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("openFile execution warning:", err);
      }
    },
    async applyChange() {
      try {
        if (!workspace || !selected)
        return;
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
        const refreshed = normalizeWorkspace(await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}`));
        const content = await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}/files?${new URLSearchParams({ path: selected.path })}`);
        setWorkspace(refreshed);
        setSelected(content);
        setEditor(content.content);
        setFeedback("修改已写入隔离工作区，尚未推送、创建 PR、合并或部署。");
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "文件修改失败。");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("applyChange execution warning:", err);
      }
    },
    beginNewFile() {
      try {
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
      } catch (err) {
        console.warn("beginNewFile execution warning:", err);
      }
    },
    async deleteSelectedFile() {
      try {
        if (!workspace || !selected?.sha256
        || !window.confirm(`删除 ${selected.path}？该操作只影响隔离工作区。`))
        return;
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
        const refreshed = normalizeWorkspace(await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}`));
        setWorkspace(refreshed);
        setSelected(null);
        setEditor("");
        setFeedback("文件已从隔离工作区删除；远端仓库未发生变化。");
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "文件删除失败。");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("deleteSelectedFile execution warning:", err);
      }
    },
    async deleteWorkspace() {
      try {
        if (!workspace || !window.confirm("删除此隔离工作区？未推送的本地修改将被移除。"))
        return;
    setBusy(true);
    setFeedback("");
    try {
        await jsonRequest(`/api/repository-workspaces/${workspace.workspaceId}`, { method: "DELETE" });
        setWorkspace(null);
        setSelected(null);
        setEditor("");
        try {
            sessionStorage.removeItem(workspaceStorageKey);
        }
        catch { /* optional */ }
        setFeedback("隔离工作区已删除；远端仓库未发生任何变化。");
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "工作区删除失败。");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("deleteWorkspace execution warning:", err);
      }
    },
    continueToProjectGeneration() {
      try {
        if (!workspace || workspace.completeness !== "COMPLETE")
        return;
    const search = new URLSearchParams({ repositoryWorkspaceId: workspace.workspaceId });
    window.location.assign(`/generation?${search}`);
      } catch (err) {
        console.warn("continueToProjectGeneration execution warning:", err);
      }
    },
    continueToTranslation() {
      try {
        if (!workspace || workspace.completeness !== "COMPLETE"
        || workspace.pendingPaths.length > 0)
        return;
    const search = new URLSearchParams({ repositoryWorkspaceId: workspace.workspaceId });
    window.location.assign(`/translation?${search}`);
      } catch (err) {
        console.warn("continueToTranslation execution warning:", err);
      }
    },
    continueToSpring() {
      try {
        if (!workspace || workspace.completeness !== "COMPLETE"
        || workspace.pendingPaths.length > 0)
        return;
    const search = new URLSearchParams({
        repositoryWorkspaceId: workspace.workspaceId,
        expectedCommitSha: workspace.currentHeadCommit,
        requestedRef: workspace.requestedRef,
    });
    window.location.assign(`/spring?${search}`);
      } catch (err) {
        console.warn("continueToSpring execution warning:", err);
      }
    },
  },
});
