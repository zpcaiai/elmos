"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Icon } from "../components/Icon";
import { RuntimeDeploymentGuide } from "../components/RuntimeDeploymentGuide";
import { StatusChip } from "../components/StatusChip";
import { useAccountSession } from "../components/AccountSessionProvider";
import type { SpringRouteDescriptor } from "../lib/contracts";
import { springDeploymentGuidance } from "../lib/deploymentGuidance";

type SourceMode = "PUBLIC_GIT" | "GITHUB_APP" | "MATERIALIZED_SNAPSHOT" | "REPOSITORY_WORKSPACE";
type RunStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "BLOCKED" | "CANCELLED";
type RuntimeStatus = "NOT_STARTED" | "STARTING" | "HEALTHY" | "UNHEALTHY" | "STOPPED";
type Stage =
  | "IMPORT_GIT" | "LOCK_SNAPSHOT" | "FINGERPRINT" | "SOURCE_BASELINE"
  | "EXTRACT_FCM" | "OPENREWRITE" | "BUILD_AND_TEST" | "DETERMINISTIC_REPAIR"
  | "INDEPENDENT_VALIDATION" | "PACKAGE_ARTIFACT" | "READY"
  | "START_APPLICATION" | "HEALTH_CHECK" | "STOP_APPLICATION";

type Capability = {
  packKey: string;
  sourceTuple: { springBoot: string; java: string; build: string };
  targetTuple: { springBoot: string; java: string; build: string };
  openRewrite: { rewriteSpring: string; mavenPlugin: string };
  routes?: SpringRouteDescriptor[];
  experimentalRoutesRequireOptIn?: boolean;
  transformerConfigured: boolean;
  transformerReason: string;
  runtimeRunnerConfigured: boolean;
  runtimeRunnerReason: string;
  independentVerifierConfigured: boolean;
  independentVerifierReason: string;
  downloadRequiresIndependentPass: boolean;
  runtimeRequiresIndependentPass: boolean;
};

type Event = {
  sequence: number;
  stage: Stage;
  status: string;
  message: string;
  observedAt: string;
};

type Run = {
  runId: string;
  retryOfRunId?: string | null;
  status: RunStatus;
  stage: Stage;
  runtimeStatus: RuntimeStatus;
  attempt: number;
  repositoryUrl?: string | null;
  requestedRef: string;
  resolvedCommitSha?: string | null;
  snapshotId?: string | null;
  snapshotDigest?: string | null;
  exactTuple: {
    sourceSpringBoot: string;
    sourceJava: string;
    sourceBuildTool: string;
    targetSpringBoot: string;
    targetJava: string;
    targetBuildTool: string;
    rewriteSpring: string;
    rewriteMavenPlugin: string;
  };
  fingerprint?: {
    springBootVersion: string;
    javaVersion: string;
    buildTool: string;
    modules: string[];
    activeCapabilities: string[];
    unknowns: string[];
  } | null;
  fcmArtifact?: string | null;
  downloadAvailable: boolean;
  artifactSha256?: string | null;
  artifactSize?: number | null;
  healthPath?: string | null;
  runtimePort?: number | null;
  failureCode?: string | null;
  failureMessage?: string | null;
  independentValidation?: {
    status: string;
    verifierId: string;
    artifactSha256: string;
    evidencePath: string;
    decidedAt: string;
  } | null;
  events: Event[];
};

type LogResponse = { runId: string; lines: string[]; truncated: boolean };
type ApiError = { errorCode?: string; message?: string; retryable?: boolean };
type ConnectedRepository = {
  repositoryId: string;
  repositoryExternalId: number;
  installationExternalId: number;
  fullName: string;
  defaultBranch: string;
  visibility: string;
};
type RepositoryCatalog = {
  status: "READY" | "NO_AUTHORIZED_REPOSITORIES" | "NOT_CONFIGURED" | "UNAVAILABLE";
  repositories: ConnectedRepository[];
  message?: string;
};
type GithubInstallationBegin = {
  status: "AWAITING_GITHUB_INSTALLATION";
  installationUrl: string;
  expiresAt: string;
};
type FeedbackKind = "success" | "error";

const latestRunStorageKey = "elmos.spring.latest-run-id";

/**
 * Stage copy quotes the exact tuple the Java engine reports. When the
 * capability contract has not been read, the copy says so rather than naming a
 * version pair the console cannot confirm.
 */
function buildStageCards(capability: Capability | null): Array<{ stages: Stage[]; title: string; detail: string }> {
  const source = capability
    ? `${capability.routes?.length ?? 1} 条声明路线；已验证点为 Boot ${capability.sourceTuple.springBoot}、`
      + `Java ${capability.sourceTuple.java}、${capability.sourceTuple.build}`
    : "契约未读取的路线目录";
  const targetJava = capability ? `Java ${capability.targetTuple.java}` : "目标 Java";
  const rewrite = capability
    ? `固定 Rewrite Spring ${capability.openRewrite.rewriteSpring} 与插件 ${capability.openRewrite.mavenPlugin}。`
    : "固定 OpenRewrite 版本由 Engine 能力契约声明；契约未读取时不展示版本号。";
  return [
    { stages: ["IMPORT_GIT"], title: "导入 Git 仓库", detail: "仅允许批准的 HTTPS Git host，拒绝 URL 凭证。" },
    { stages: ["LOCK_SNAPSHOT"], title: "锁定 Commit / Snapshot", detail: "解析 40 位 Commit，并生成确定性内容摘要。" },
    { stages: ["FINGERPRINT"], title: "精确版本识别", detail: `按 Boot、JDK 与构建工具从 ${source} 中选择，不做模糊匹配。` },
    { stages: ["SOURCE_BASELINE"], title: "源工程基线", detail: "在一次性副本中使用检测到且已配置的精确源 JDK 执行完整构建与测试。" },
    { stages: ["EXTRACT_FCM"], title: "提取 FCM", detail: "在转换前固化能力、来源映射、默认值与未知项。" },
    { stages: ["OPENREWRITE"], title: "OpenRewrite 实际转换", detail: rewrite },
    { stages: ["BUILD_AND_TEST", "DETERMINISTIC_REPAIR"], title: "编译 / 测试 / 修复", detail: `${targetJava} 真实测试；失败时最多一次确定性修复。` },
    { stages: ["PACKAGE_ARTIFACT"], title: "候选项目打包", detail: "生成内容寻址 ZIP，尚不自动开放下载。" },
    { stages: ["INDEPENDENT_VALIDATION"], title: "独立验证", detail: "另一验证器从 ZIP 新目录解包并执行 mvn verify。" },
    { stages: ["READY"], title: "下载新项目", detail: "只有独立 PASS 后才开放下载。" },
    { stages: ["START_APPLICATION", "HEALTH_CHECK"], title: "一键隔离启动", detail: `${targetJava} 启动、回环健康检查，未配置 Rootless 时拒绝。` },
    { stages: ["STOP_APPLICATION"], title: "日志 / 停止 / 重试", detail: "实时脱敏日志、优雅停止与新的可追溯尝试。" },
  ];
}

const orderedStages: Stage[] = [
  "IMPORT_GIT", "LOCK_SNAPSHOT", "FINGERPRINT", "SOURCE_BASELINE", "EXTRACT_FCM",
  "OPENREWRITE", "BUILD_AND_TEST", "DETERMINISTIC_REPAIR", "PACKAGE_ARTIFACT",
  "INDEPENDENT_VALIDATION", "READY", "START_APPLICATION", "HEALTH_CHECK", "STOP_APPLICATION",
];

function randomKey(prefix: string) {
  return `${prefix}-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`}`;
}

function shortDigest(value?: string | null) {
  return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "等待生成";
}

function formatBytes(value?: number | null) {
  if (!value) return "等待生成";
  return value < 1024 * 1024 ? `${Math.ceil(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`;
}

type SpringCredentials = { tenantId: string; actorId: string; token: string };

async function api<T>(url: string, init?: RequestInit, credentials?: SpringCredentials): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    ...init,
    headers: {
      ...init?.headers,
      ...(credentials ? {
        authorization: `Bearer ${credentials.token}`,
        "x-elmos-tenant": credentials.tenantId,
        "x-elmos-actor": credentials.actorId,
      } : {}),
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as ApiError;
    throw new Error(`${error.errorCode ?? `HTTP_${response.status}`}: ${error.message ?? "请求失败"}`);
  }
  return response.json() as Promise<T>;
}

export function SpringModernizationStudio() {
  const account = useAccountSession();
  const [sourceMode, setSourceMode] = useState<SourceMode>("PUBLIC_GIT");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [requestedRef, setRequestedRef] = useState("main");
  const [expectedCommitSha, setExpectedCommitSha] = useState("");
  const [snapshotId, setSnapshotId] = useState("");
  const [materializedRelativePath, setMaterializedRelativePath] = useState("");
  const [repositoryWorkspaceId, setRepositoryWorkspaceId] = useState("");
  const [githubRepositories, setGithubRepositories] = useState<ConnectedRepository[]>([]);
  const [githubRepositoryId, setGithubRepositoryId] = useState("");
  const [githubCatalogStatus, setGithubCatalogStatus] =
    useState<RepositoryCatalog["status"]>("NOT_CONFIGURED");
  const [startAfterVerification, setStartAfterVerification] = useState(false);
  const [capability, setCapability] = useState<Capability | null>(null);
  const [capabilityError, setCapabilityError] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [logs, setLogs] = useState<LogResponse | null>(null);
  const [showLogs, setShowLogs] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [feedbackKind, setFeedbackKind] = useState<FeedbackKind>("success");
  const [tenantId, setTenantId] = useState("");
  const [actorId, setActorId] = useState("");
  const [proxyToken, setProxyToken] = useState("");
  const [recoveryRunId, setRecoveryRunId] = useState("");

  const accountRunner = account.status === "authenticated"
    && account.principal?.permissions.includes("spring:execute") === true;
  const credentials = useMemo(
    () => accountRunner
      ? undefined
      : { tenantId: tenantId.trim(), actorId: actorId.trim(), token: proxyToken },
    [accountRunner, actorId, proxyToken, tenantId],
  );

  useEffect(() => {
    if (!accountRunner || !account.principal) return;
    setTenantId(account.principal.organizationId);
    setActorId(account.principal.actorId);
  }, [account.principal, accountRunner]);

  const notify = useCallback((message: string, kind: FeedbackKind = "success") => {
    setFeedback(message);
    setFeedbackKind(kind);
  }, []);

  const refreshGithubCatalog = useCallback(async () => {
    const catalog = await api<RepositoryCatalog>("/api/github-repositories", undefined, credentials);
    setGithubCatalogStatus(catalog.status);
    setGithubRepositories(catalog.repositories);
    const first = catalog.repositories[0];
    if (first) {
      setGithubRepositoryId((value) => value || first.repositoryId);
      setRequestedRef((value) => value || first.defaultBranch);
    }
    return catalog;
  }, [credentials]);

  const refresh = useCallback(async (runId: string, includeLogs = showLogs) => {
    const next = await api<Run>(`/api/spring-upgrades/${runId}`, undefined, credentials);
    setRun(next);
    window.sessionStorage.setItem(latestRunStorageKey, next.runId);
    if (includeLogs) {
      setLogs(await api<LogResponse>(`/api/spring-upgrades/${runId}/logs`, undefined, credentials));
    }
    return next;
  }, [credentials, showLogs]);

  useEffect(() => {
    api<Capability>("/api/spring-upgrades/capabilities")
      .then((value) => {
        setCapability(value);
        setCapabilityError("");
      })
      .catch((error: Error) => {
        setCapability(null);
        setCapabilityError(error.message);
        notify(error.message, "error");
      });
  }, [notify]);

  useEffect(() => {
    refreshGithubCatalog()
      .catch(() => {
        setGithubCatalogStatus("NOT_CONFIGURED");
        setGithubRepositories([]);
      });
  }, [refreshGithubCatalog]);

  useEffect(() => {
    const runId = window.sessionStorage.getItem(latestRunStorageKey);
    if (runId && /^[0-9a-f-]{36}$/i.test(runId)) setRecoveryRunId(runId);
    const parameters = new URLSearchParams(window.location.search);
    const workspaceId = parameters.get("repositoryWorkspaceId")?.trim().toLowerCase() ?? "";
    const commit = parameters.get("expectedCommitSha")?.trim().toLowerCase() ?? "";
    const ref = parameters.get("requestedRef")?.trim() ?? "";
    if (/^[0-9a-f-]{36}$/.test(workspaceId) && /^[0-9a-f]{40}$/.test(commit)) {
      setRepositoryWorkspaceId(workspaceId);
      setExpectedCommitSha(commit);
      if (ref) setRequestedRef(ref);
      setSourceMode("REPOSITORY_WORKSPACE");
    }
  }, []);

  useEffect(() => {
    if (!run || !["QUEUED", "RUNNING"].includes(run.status) && run.runtimeStatus !== "STARTING") return;
    const timer = window.setInterval(() => {
      refresh(run.runId).catch((error: Error) => notify(error.message, "error"));
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [notify, refresh, run]);

  useEffect(() => {
    if (!feedback || feedbackKind === "error") return;
    const timer = window.setTimeout(() => setFeedback(""), 6_000);
    return () => window.clearTimeout(timer);
  }, [feedback, feedbackKind]);

  const githubSourceReady = sourceMode !== "GITHUB_APP"
    || githubCatalogStatus === "READY" && Boolean(githubRepositoryId);
  const runnerReady = Boolean(
    capability?.transformerConfigured
    && capability?.independentVerifierConfigured
    && githubSourceReady,
  );
  const credentialsReady = accountRunner || tenantId.trim().length >= 3
    && actorId.trim().length >= 3
    && proxyToken.length >= 24;
  const runtimeReady = Boolean(capability?.runtimeRunnerConfigured);
  const lastStageIndex = run ? orderedStages.indexOf(run.stage) : -1;
  // The exact tuple is owned by the Java engine capability contract. Until it
  // has been read, the page shows that it is unknown instead of printing a
  // version pair the console has not observed.
  const lockedRouteLabel = capability
    ? `${capability.routes?.length ?? 1} 条精确源路线 → Spring Boot ${capability.targetTuple.springBoot}`
      + ` / Java ${capability.targetTuple.java}；已验证点 Boot ${capability.sourceTuple.springBoot}`
      + ` / Java ${capability.sourceTuple.java}`
    : "精确转换路线未读取（UNKNOWN）";
  const stageCards = useMemo(() => buildStageCards(capability), [capability]);
  const artifactFileName = capability
    ? `migrated-spring-boot-${capability.targetTuple.springBoot}.zip`
    : "migrated-spring-boot.zip";

  const stageStatus = useCallback((stages: Stage[]) => {
    if (!run) return "NOT_RUN";
    const matching = run.events.filter((event) => stages.includes(event.stage));
    if (matching.some((event) => ["FAILED", "BLOCKED", "CANCELLED"].includes(event.status))) return "BLOCKED";
    if (matching.some((event) => event.status === "PASS")) return "READY";
    const greatest = Math.max(...stages.map((stage) => orderedStages.indexOf(stage)));
    if (matching.length > 0 && greatest < lastStageIndex) return "READY";
    if (stages.includes(run.stage) && ["QUEUED", "RUNNING"].includes(run.status)) return "REVIEW";
    if (stages.includes("READY") && run.downloadAvailable) return "READY";
    if (stages.includes("HEALTH_CHECK") && run.runtimeStatus === "HEALTHY") return "READY";
    if (stages.includes("STOP_APPLICATION") && run.runtimeStatus === "STOPPED") return "READY";
    return "NOT_RUN";
  }, [lastStageIndex, run]);

  const currentMessage = useMemo(() => {
    if (!run) return runnerReady
      ? "Runner 与独立验证器已配置，可以提交精确路线。"
      : capabilityError || capability?.transformerReason || "正在读取 Runner 能力。";
    if (run.failureCode) return `${run.failureCode} · ${run.failureMessage ?? "流程已安全阻断"}`;
    return run.events.at(-1)?.message ?? "等待执行状态";
  }, [capability, capabilityError, run, runnerReady]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setFeedback("");
    try {
      const next = await api<Run>("/api/spring-upgrades", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          sourceMode,
          repositoryUrl: sourceMode === "PUBLIC_GIT" ? repositoryUrl.trim() : null,
          repositoryId: sourceMode === "GITHUB_APP" ? githubRepositoryId : null,
          repositoryWorkspaceId: sourceMode === "REPOSITORY_WORKSPACE"
            ? repositoryWorkspaceId.trim()
            : null,
          requestedRef: sourceMode === "MATERIALIZED_SNAPSHOT"
            ? "snapshot"
            : requestedRef.trim(),
          expectedCommitSha: sourceMode === "GITHUB_APP"
            ? null
            : expectedCommitSha.trim() || null,
          snapshotId: sourceMode === "MATERIALIZED_SNAPSHOT"
            ? snapshotId.trim()
            : null,
          materializedRelativePath: sourceMode === "MATERIALIZED_SNAPSHOT" ? materializedRelativePath.trim() : null,
          startAfterVerification,
          idempotencyKey: randomKey("spring-upgrade"),
        }),
      }, credentials);
      setRun(next);
      window.sessionStorage.setItem(latestRunStorageKey, next.runId);
      setLogs(null);
      notify("迁移已排队；页面会持续读取真实阶段和证据状态。");
    } catch (error) {
      notify(error instanceof Error ? error.message : "提交失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function connectGithubApp() {
    setBusy(true);
    setFeedback("");
    try {
      const result = await api<GithubInstallationBegin>("/api/github-installation", {
        method: "POST",
      }, credentials);
      const target = new URL(result.installationUrl);
      if (target.protocol !== "https:" || target.hostname !== "github.com") {
        throw new Error("GITHUB_APP_INSTALL_URL_INVALID: 安装地址未通过安全校验");
      }
      window.location.assign(target.toString());
    } catch (error) {
      notify((error as Error).message, "error");
      setBusy(false);
    }
  }

  async function lifecycle(path: string, body?: object) {
    if (!run) return;
    setBusy(true);
    try {
      const next = await api<Run>(`/api/spring-upgrades/${run.runId}/${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body ?? {}),
      }, credentials);
      setRun(next);
      window.sessionStorage.setItem(latestRunStorageKey, next.runId);
      notify("操作已受理，状态将自动刷新。");
    } catch (error) {
      notify(error instanceof Error ? error.message : "操作失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function toggleLogs() {
    if (!run) return;
    const next = !showLogs;
    setShowLogs(next);
    if (next) {
      try {
        setLogs(await api<LogResponse>(`/api/spring-upgrades/${run.runId}/logs`, undefined, credentials));
      } catch (error) {
        notify(error instanceof Error ? error.message : "日志不可用", "error");
      }
    }
  }

  async function downloadArtifact() {
    if (!run?.downloadAvailable || !run.artifactSha256 || !run.artifactSize) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/spring-upgrades/${run.runId}/artifact`, {
        cache: "no-store",
        headers: accountRunner ? undefined : {
          authorization: `Bearer ${proxyToken}`,
          "x-elmos-tenant": tenantId.trim(),
          "x-elmos-actor": actorId.trim(),
        },
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({})) as ApiError;
        throw new Error(`${error.errorCode ?? `HTTP_${response.status}`}: ${error.message ?? "归档不可用"}`);
      }
      const responseDigest = response.headers.get("x-content-sha256");
      const declaredLength = Number(response.headers.get("content-length"));
      const blob = await response.blob();
      const actualDigest = [...new Uint8Array(await crypto.subtle.digest(
        "SHA-256",
        await blob.arrayBuffer(),
      ))].map((value) => value.toString(16).padStart(2, "0")).join("");
      if (
        responseDigest !== run.artifactSha256
        || actualDigest !== run.artifactSha256
        || blob.size !== run.artifactSize
        || !Number.isSafeInteger(declaredLength)
        || declaredLength !== blob.size
      ) {
        throw new Error("ARTIFACT_INTEGRITY_MISMATCH: 下载字节与独立验证证据不一致");
      }
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = artifactFileName;
      anchor.click();
      URL.revokeObjectURL(url);
      notify("ZIP 的长度和 SHA-256 已在浏览器复算并与独立验证证据一致。");
    } catch (error) {
      notify(error instanceof Error ? error.message : "归档下载失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function recoverRun() {
    if (!/^[0-9a-f-]{36}$/i.test(recoveryRunId) || !credentialsReady) return;
    setBusy(true);
    try {
      await refresh(recoveryRunId.toLowerCase(), false);
      notify("已按 Run UUID 与当前租户身份恢复持久迁移运行。");
    } catch (error) {
      notify(error instanceof Error ? error.message : "SPRING_UPGRADE_RUN_NOT_FOUND", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-stack business-page">
      <section className="page-header business-hero">
        <div>
          <span className="overline">SPRING MODERNIZATION · REAL JOURNEY</span>
          <h1>Java / Spring 老项目一键迁移</h1>
          <p>从不可变 Git Commit 到 FCM、真实 OpenRewrite、双工具链构建、独立验证、下载与隔离启动。每一步都显示真实状态，未运行绝不显示通过。</p>
        </div>
        <div className="header-actions">
          <StatusChip status={runnerReady ? "READY" : "NOT_CONFIGURED"} />
          <StatusChip status={run?.status ?? "NOT_RUN"} />
        </div>
      </section>

      <section className={`source-notice ${runnerReady ? "" : "runner-warning"}`} role="status">
        <Icon name={runnerReady ? "shield" : "lock"} size={16} />
        <span>{currentMessage}</span>
        <StatusChip status={runnerReady ? "ENFORCED" : "BLOCKED"} compact />
      </section>

      <section className="metric-grid metric-grid-four" aria-label="精确迁移路线">
        <article className="metric-card">
          <span>精确源路线</span>
          <strong className={`metric-word ${capability ? "" : "warning-text"}`}>{capability ? `${capability.routes?.length ?? 1} 条` : "UNKNOWN"}</strong>
          <small>{capability ? `1 个已验证点：Boot ${capability.sourceTuple.springBoot} · Java ${capability.sourceTuple.java}` : "能力契约未读取"}</small>
        </article>
        <article className="metric-card">
          <span>目标版本</span>
          <strong className={`metric-word ${capability ? "" : "warning-text"}`}>{capability ? `Boot ${capability.targetTuple.springBoot}` : "UNKNOWN"}</strong>
          <small>{capability ? `Java ${capability.targetTuple.java} · ${capability.targetTuple.build}` : "能力契约未读取"}</small>
        </article>
        <article className="metric-card">
          <span>OpenRewrite</span>
          <strong className={`metric-word ${capability ? "" : "warning-text"}`}>{capability?.openRewrite.rewriteSpring ?? "UNKNOWN"}</strong>
          <small>{capability ? `Plugin ${capability.openRewrite.mavenPlugin} · 固定 Recipes` : "能力契约未读取"}</small>
        </article>
        <article className="metric-card"><span>独立裁判</span><strong className={`metric-word ${run?.independentValidation?.status === "PASS" ? "" : "warning-text"}`}>{run?.independentValidation?.status ?? "NOT_RUN"}</strong><small>从下载 ZIP 重新验证</small></article>
      </section>

      <div className="business-layout">
        <form className="surface-card business-form" onSubmit={submit}>
          <div className="business-section-heading">
            <div><span className="overline">IMMUTABLE INPUT</span><h2>导入并锁定源仓库</h2></div>
            <StatusChip status={run ? run.status : "DRAFT"} compact />
          </div>
          <div className="business-form-grid">
            <label>
              <span>租户标识</span>
              <input aria-label="Spring 租户标识" value={tenantId} onChange={(event) => setTenantId(event.target.value)} readOnly={accountRunner} autoComplete="off" />
            </label>
            <label>
              <span>执行者标识</span>
              <input aria-label="Spring 执行者标识" value={actorId} onChange={(event) => setActorId(event.target.value)} readOnly={accountRunner} autoComplete="off" />
            </label>
            {accountRunner ? (
              <div className="locked-target spring-field-wide"><span>账户授权</span><strong>企业 OIDC · spring:execute</strong><small>租户和执行者来自已验证声明。</small></div>
            ) : (
              <label className="spring-field-wide">
                <span>Spring 代理短期令牌</span>
                <input aria-label="Spring 代理短期令牌" type="password" value={proxyToken} onChange={(event) => setProxyToken(event.target.value)} autoComplete="off" />
                <small>仅限本地开发；令牌最多 24 小时，并与唯一租户和 Actor 绑定。</small>
              </label>
            )}
            <label>
              <span>输入方式</span>
              <select value={sourceMode} onChange={(event) => setSourceMode(event.target.value as SourceMode)}>
                <option value="PUBLIC_GIT">公开 HTTPS Git</option>
                <option value="GITHUB_APP">GitHub App 私有仓库</option>
                <option value="REPOSITORY_WORKSPACE">ELMOS 受控仓库工作区</option>
                <option value="MATERIALIZED_SNAPSHOT">受控 Snapshot Workspace</option>
              </select>
            </label>
            {sourceMode === "PUBLIC_GIT" ? (
              <>
                <label className="spring-field-wide"><span>Git 仓库 URL</span><input required type="url" value={repositoryUrl} onChange={(event) => setRepositoryUrl(event.target.value)} placeholder="https://github.com/org/repo.git" /></label>
                <label><span>Branch / Tag</span><input required value={requestedRef} onChange={(event) => setRequestedRef(event.target.value)} placeholder="main 或 refs/tags/v1.0.0" /></label>
                <label><span>预期 Commit（可选）</span><input value={expectedCommitSha} onChange={(event) => setExpectedCommitSha(event.target.value.toLowerCase())} pattern="[0-9a-f]{40}" placeholder="40 位 SHA；填写后必须完全匹配" /></label>
              </>
            ) : sourceMode === "GITHUB_APP" ? (
              <>
                <label className="spring-field-wide">
                  <span>已授权 GitHub 仓库</span>
                  <select
                    required
                    value={githubRepositoryId}
                    onChange={(event) => {
                      const repositoryId = event.target.value;
                      setGithubRepositoryId(repositoryId);
                      const selected = githubRepositories.find(
                        (repository) => repository.repositoryId === repositoryId,
                      );
                      if (selected) setRequestedRef(selected.defaultBranch);
                    }}
                    disabled={githubCatalogStatus !== "READY"}
                  >
                    {githubRepositories.length === 0
                      ? <option value="">没有可用的已授权仓库</option>
                      : githubRepositories.map((repository) => (
                          <option
                            key={repository.repositoryId}
                            value={repository.repositoryId}
                          >
                            {repository.fullName} · {repository.visibility}
                          </option>
                        ))}
                  </select>
                </label>
                <label>
                  <span>Branch / Tag</span>
                  <input
                    required
                    value={requestedRef}
                    onChange={(event) => setRequestedRef(event.target.value)}
                    placeholder="main 或 refs/tags/v1.0.0"
                  />
                </label>
                <div className="locked-target">
                  <span>GitHub App 状态</span>
                  <strong>{githubCatalogStatus}</strong>
                  <small>
                    仅使用仓库级、最长 1 小时的短期 Token；Token 不进入
                    Transformer、日志或 Snapshot。
                  </small>
                </div>
                <div className="business-actions spring-field-wide">
                  <button
                    className="button button-secondary"
                    type="button"
                    disabled={busy}
                    onClick={connectGithubApp}
                  >
                    <Icon name="repository" size={16} />
                    安装 / 更新 GitHub App
                  </button>
                  <button
                    className="button button-ghost"
                    type="button"
                    disabled={busy}
                    onClick={() => refreshGithubCatalog()
                      .then(() => notify("已刷新授权仓库"))
                      .catch((error: Error) => notify(error.message, "error"))}
                  >
                    刷新授权仓库
                  </button>
                </div>
              </>
            ) : sourceMode === "REPOSITORY_WORKSPACE" ? (
              <>
                <label className="spring-field-wide">
                  <span>仓库工作区 UUID</span>
                  <input required value={repositoryWorkspaceId}
                    onChange={(event) => setRepositoryWorkspaceId(event.target.value.toLowerCase())}
                    pattern="[0-9a-f-]{36}" placeholder="从代码仓库工作区交接" />
                </label>
                <label>
                  <span>Branch / Tag</span>
                  <input required value={requestedRef}
                    onChange={(event) => setRequestedRef(event.target.value)}
                    placeholder="main" />
                </label>
                <label>
                  <span>精确 HEAD Commit</span>
                  <input required value={expectedCommitSha}
                    onChange={(event) => setExpectedCommitSha(event.target.value.toLowerCase())}
                    pattern="[0-9a-f]{40}" placeholder="必须与工作区当前 HEAD 完全一致" />
                </label>
              </>
            ) : (
              <>
                <label><span>Snapshot ID</span><input required value={snapshotId} onChange={(event) => setSnapshotId(event.target.value)} /></label>
                <label><span>Workspace 相对路径</span><input required value={materializedRelativePath} onChange={(event) => setMaterializedRelativePath(event.target.value)} placeholder="snapshots/..." /></label>
                <label className="spring-field-wide"><span>绑定 Commit</span><input required value={expectedCommitSha} onChange={(event) => setExpectedCommitSha(event.target.value.toLowerCase())} pattern="[0-9a-f]{40}" placeholder="必须为 40 位 SHA" /></label>
              </>
            )}
            <div className="locked-target spring-field-wide">
              <span>锁定转换路线</span>
              <strong>{lockedRouteLabel}</strong>
              <small>
                {capability
                  ? `路线来自 Engine 能力契约 ${capability.packKey}；构建工具限定 ${capability.sourceTuple.build}，`
                    + "版本不精确匹配会在 FINGERPRINT 阶段 fail closed，不做模糊升级。"
                  : "Engine 能力契约尚未读取；在读取到精确版本元组之前，页面不展示任何具体版本号。"}
              </small>
            </div>
          </div>
          <label className="spring-start-toggle">
            <input type="checkbox" checked={startAfterVerification} disabled={!runtimeReady} onChange={(event) => setStartAfterVerification(event.target.checked)} />
            <span><strong>验证通过后自动一键启动</strong><small>{runtimeReady ? "独立验证 PASS 后，在每次运行专属的 Rootless 容器中执行。" : capability?.runtimeRunnerReason ?? "独立 Runtime Runner 尚未配置。"}</small></span>
          </label>
          <div className="business-actions">
            <button className="button button-primary" type="submit" disabled={busy || !runnerReady || !credentialsReady}>
              <Icon name={busy ? "refresh" : "workflow"} size={16} className={busy ? "spinning" : undefined} />
              {!runnerReady ? "隔离 Runner 未配置" : credentialsReady ? "开始真实迁移" : "登录企业账户或填写本地短期身份"}
            </button>
            {run && ["QUEUED", "RUNNING"].includes(run.status) && <button className="button button-secondary" type="button" onClick={() => lifecycle("cancel")} disabled={busy}>取消迁移</button>}
          </div>
        </form>

        <aside className="surface-card business-summary spring-run-summary">
          <div className="business-section-heading"><div><span className="overline">RUN EVIDENCE</span><h2>运行与交付</h2></div><StatusChip status={run?.runtimeStatus ?? "NOT_RUN"} compact /></div>
          <dl className="spring-run-facts">
            <div><dt>Run / Attempt</dt><dd>{run ? `${run.runId.slice(0, 8)} · #${run.attempt}` : "尚未创建"}</dd></div>
            <div><dt>Commit</dt><dd title={run?.resolvedCommitSha ?? undefined}>{shortDigest(run?.resolvedCommitSha)}</dd></div>
            <div><dt>Snapshot</dt><dd title={run?.snapshotDigest ?? undefined}>{shortDigest(run?.snapshotDigest)}</dd></div>
            <div><dt>FCM</dt><dd>{run?.fcmArtifact ?? "NOT_RUN"}</dd></div>
            <div><dt>Artifact</dt><dd>{formatBytes(run?.artifactSize)} · {shortDigest(run?.artifactSha256)}</dd></div>
            <div><dt>Health</dt><dd>{run?.runtimeStatus === "HEALTHY" ? `127.0.0.1:${run.runtimePort}${run.healthPath}` : run?.runtimeStatus ?? "NOT_RUN"}</dd></div>
          </dl>
          <div className="business-form-grid">
            <label className="spring-field-wide">
              <span>恢复 Run UUID</span>
              <input value={recoveryRunId} onChange={(event) => setRecoveryRunId(event.target.value.toLowerCase())} pattern="[0-9a-f-]{36}" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
            </label>
          </div>
          <div className="business-actions">
            <button className="button button-secondary" type="button" disabled={busy || !credentialsReady || !/^[0-9a-f-]{36}$/i.test(recoveryRunId)} onClick={() => void recoverRun()}>
              <Icon name="refresh" size={15} />恢复运行
            </button>
          </div>
          <div className="locked-target">
            <span>隔离 Runtime Runner</span>
            <strong>{runtimeReady ? "READY · 可一键启动" : "BLOCKED · 不降级执行"}</strong>
            <small>{capability?.runtimeRunnerReason ?? "正在读取 Runtime Runner 能力。"}</small>
          </div>
          {run?.fingerprint && (
            <div className="spring-fingerprint">
              <strong>检测结果</strong>
              <span>{run.fingerprint.springBootVersion} · Java {run.fingerprint.javaVersion} · {run.fingerprint.buildTool}</span>
              <small>能力：{run.fingerprint.activeCapabilities.join("、") || "未识别"}</small>
              {run.fingerprint.unknowns.length > 0 && <small className="warning-text">未知项：{run.fingerprint.unknowns.join("、")}</small>}
            </div>
          )}
          <div className="spring-delivery-actions">
            {run?.downloadAvailable
              ? <button
                  className="button button-primary"
                  type="button"
                  disabled={busy}
                  onClick={() => void downloadArtifact()}
                ><Icon name="file" size={15} />下载新项目 ZIP</button>
              : <button className="button button-primary" disabled><Icon name="lock" size={15} />独立验证后下载</button>}
            <button className="button button-secondary" type="button" disabled={!runtimeReady || !run || !run.downloadAvailable || busy || run.runtimeStatus === "STARTING" || run.runtimeStatus === "HEALTHY"} onClick={() => lifecycle("runtime/start")}><Icon name="server" size={15} />一键启动</button>
            <button className="button button-secondary" type="button" disabled={!run || busy || !["STARTING", "HEALTHY", "UNHEALTHY"].includes(run.runtimeStatus)} onClick={() => lifecycle("runtime/stop")}>停止</button>
            <button className="button button-secondary" type="button" disabled={!run || busy || !["FAILED", "BLOCKED", "CANCELLED"].includes(run.status)} onClick={() => lifecycle("retry", { idempotencyKey: randomKey("retry") })}><Icon name="refresh" size={15} />重试</button>
            <button className="button button-secondary" type="button" disabled={!run} onClick={toggleLogs}><Icon name="file" size={15} />{showLogs ? "收起日志" : "查看日志"}</button>
          </div>
        </aside>
      </div>

      <section className="surface-card spring-route-catalog" aria-labelledby="spring-route-catalog-title">
        <div className="business-section-heading">
          <div>
            <span className="overline">LEGACY SOURCE LINES</span>
            <h2 id="spring-route-catalog-title">支持的遗留版本路线</h2>
          </div>
          <StatusChip status={capability?.routes?.length ? "READY" : "NOT_RUN"} compact />
        </div>
        <p className="spring-route-intro">
          指纹阶段按下表选择路线，而不是断言单一版本。只有带 PASSED_LOCAL 的元组有已记录的端到端本地执行证据；
          其余元组即使在受支持区间内，也保持 NOT_RUN，需要 Runner 显式开启实验路线才会执行。
        </p>
        {capability?.routes?.length
          ? (
            <div
              className="spring-route-table"
              role="table"
              aria-label="Spring 遗留版本路线目录"
              tabIndex={0}
            >
              <div className="spring-route-row spring-route-head" role="row">
                <span role="columnheader">源版本区间</span>
                <span role="columnheader">源 JDK</span>
                <span role="columnheader">构建工具</span>
                <span role="columnheader">目标</span>
                <span role="columnheader">证据</span>
              </div>
              {capability.routes.map((route) => (
                <div
                  className={`spring-route-row ${route.evidenceStatus === "PASSED_LOCAL" ? "spring-route-verified" : ""}`}
                  role="row"
                  key={route.routeId}
                >
                  <span role="cell" title={`${route.routeId}${route.notes ? ` · ${route.notes}` : ""}`}>
                    Boot [{route.sourceBootMinInclusive}, {route.sourceBootMaxExclusive})
                  </span>
                  <span role="cell">{route.sourceJavaVersions.join(" / ")}</span>
                  <span role="cell">{route.buildTool}</span>
                  <span role="cell">Boot {route.targetSpringBoot} · Java {route.targetJava}</span>
                  <span role="cell">
                    {route.evidenceStatus === "PASSED_LOCAL"
                      ? `PASSED_LOCAL @ ${route.verifiedSourceSpringBoot} / Java ${route.verifiedSourceJava}`
                      : route.evidenceStatus}
                  </span>
                </div>
              ))}
            </div>
          )
          : <p className="route-empty-detail">Engine 能力契约尚未返回路线目录；页面不会推断支持范围。</p>}
      </section>

      <RuntimeDeploymentGuide
        id="spring-runtime-deployment"
        guidance={springDeploymentGuidance}
      />

      <section className="surface-card journey-card" aria-labelledby="real-spring-journey">
        <div className="business-section-heading">
          <div><span className="overline">EVIDENCE-BOUND PIPELINE</span><h2 id="real-spring-journey">完整真实旅程</h2></div>
          <small>阶段来自 Java Engine Worker 实际事件，不由前端模拟</small>
        </div>
        <ol className="journey-grid spring-real-journey">
          {stageCards.map((card, index) => (
            <li key={card.title}>
              <i>{index + 1}</i>
              <div><strong>{card.title}</strong><span>{card.detail}</span><small>{run?.events.filter((event) => card.stages.includes(event.stage)).at(-1)?.message ?? "等待前置 Gate"}</small></div>
              <StatusChip status={stageStatus(card.stages)} compact />
            </li>
          ))}
        </ol>
      </section>

      {showLogs && (
        <section className="surface-card spring-log-card" aria-live="polite">
          <div className="business-section-heading">
            <div><span className="overline">REDACTED RUN LOG</span><h2>转换与运行日志</h2></div>
            <button className="button button-secondary" type="button" onClick={() => run && refresh(run.runId, true)}><Icon name="refresh" size={14} />刷新</button>
          </div>
          <pre>{logs?.lines.join("\n") || "日志尚未产生。"}</pre>
          {logs?.truncated && <small>仅显示最近的受限日志窗口；敏感模式已经脱敏。</small>}
        </section>
      )}

      <div
        className={`feedback-toast ${feedbackKind === "error" ? "feedback-error" : ""} ${feedback ? "visible" : ""}`}
        role={feedbackKind === "error" ? "alert" : "status"}
        aria-live={feedbackKind === "error" ? "assertive" : "polite"}
        aria-atomic="true"
      >
        <span><Icon name={feedbackKind === "error" ? "lock" : "check"} size={17} /></span>
        <span className="feedback-message">{feedback}</span>
        {feedbackKind === "error" && feedback && (
          <button type="button" aria-label="关闭错误提示" onClick={() => setFeedback("")}>
            <Icon name="close" size={15} />
          </button>
        )}
      </div>
    </div>
  );
}
