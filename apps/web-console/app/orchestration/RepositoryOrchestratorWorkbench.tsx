"use client";

import { useEffect, useMemo, useState } from "react";

import {
  parseRepositoryModelCatalog,
  parseRepositoryPreflightResult,
  type RepositoryModelCatalog,
  type RepositoryPreflightRequest,
  type RepositoryPreflightResult,
  type RepositoryRiskLevel,
  type RepositoryRiskProfile,
} from "../lib/repositoryOrchestratorContracts";
import styles from "./RepositoryOrchestratorWorkbench.module.css";

type Mode = "smart" | "manual";

const initialRisk: RepositoryRiskProfile = {
  security: "low",
  dataMigration: "low",
  concurrency: "low",
  publicContract: "low",
  blastRadius: "low",
  longHorizon: false,
};

const riskOptions: RepositoryRiskLevel[] = ["none", "low", "medium", "high", "critical"];

function readableReason(reason: string): string {
  return reason.replaceAll("_", " ").replaceAll(":", " · ");
}

function statusTone(status: string): "blocked" | "pending" | "ready" {
  if (status === "BLOCKED" || status === "NOT_CONFIGURED") return "blocked";
  if (status.startsWith("READY")) return "ready";
  return "pending";
}

async function responseJson(response: Response): Promise<unknown> {
  const mediaType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (mediaType !== "application/json") throw new Error("REPOSITORY_RESPONSE_MEDIA_TYPE_INVALID");
  return response.json() as Promise<unknown>;
}

function failureMessage(value: unknown, fallback: string): string {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return fallback;
  const message = (value as Record<string, unknown>).message;
  return typeof message === "string" && message.trim() ? message : fallback;
}

export function RepositoryOrchestratorWorkbench() {
  const [catalog, setCatalog] = useState<RepositoryModelCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<Mode>("smart");
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [fallbackEnabled, setFallbackEnabled] = useState(false);
  const [optimizationProfile, setOptimizationProfile] = useState<RepositoryPreflightRequest["optimizationProfile"]>("cost_performance");
  const [verificationPolicy, setVerificationPolicy] = useState<RepositoryPreflightRequest["verificationPolicy"]>("system_required_verifiers");
  const [risk, setRisk] = useState<RepositoryRiskProfile>(initialRisk);
  const [result, setResult] = useState<RepositoryPreflightResult | null>(null);
  const [preflightError, setPreflightError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    async function loadCatalog() {
      setLoading(true);
      setCatalogError(null);
      try {
        const response = await fetch("/api/repository-orchestrator/models", {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: controller.signal,
        });
        const raw = await responseJson(response);
        if (!response.ok) throw new Error(failureMessage(raw, "模型目录当前不可用。"));
        const parsed = parseRepositoryModelCatalog(raw);
        setCatalog(parsed);
        setMode(parsed.defaultMode);
        setOptimizationProfile(parsed.optimizationProfiles[0]);
        setVerificationPolicy(parsed.verificationPolicies[0]);
      } catch (error) {
        if (controller.signal.aborted) return;
        setCatalogError(error instanceof Error ? error.message : "模型目录当前不可用。");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void loadCatalog();
    return () => controller.abort();
  }, []);

  const selectedDescriptor = useMemo(
    () => catalog?.models.find((model) => model.alias === selectedModel) ?? null,
    [catalog, selectedModel],
  );
  const canPreflight = Boolean(catalog)
    && !submitting
    && (mode === "smart" || Boolean(selectedDescriptor?.selectable));

  function updateRisk(field: keyof Omit<RepositoryRiskProfile, "longHorizon">, value: RepositoryRiskLevel) {
    setRisk((current) => ({ ...current, [field]: value }));
    setResult(null);
  }

  async function submitPreflight() {
    if (!catalog || !canPreflight) return;
    const request: RepositoryPreflightRequest = {
      schemaVersion: "1.0",
      catalogVersion: catalog.catalogVersion,
      selectionVersion: catalog.selectionVersion,
      mode,
      selectedModel: mode === "manual" ? selectedModel : null,
      optimizationProfile,
      fallbackPolicy: mode === "manual"
        ? fallbackEnabled ? "smart_within_allowlist" : "strict"
        : null,
      verificationPolicy,
      risk,
    };
    setSubmitting(true);
    setPreflightError(null);
    setResult(null);
    try {
      const response = await fetch("/api/repository-orchestrator/preflight", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(request),
        cache: "no-store",
      });
      const raw = await responseJson(response);
      if (!response.ok && response.status !== 400) {
        throw new Error(failureMessage(raw, "仓库编排预检当前不可用。"));
      }
      setResult(parseRepositoryPreflightResult(raw));
    } catch (error) {
      setPreflightError(error instanceof Error ? error.message : "仓库编排预检当前不可用。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className={styles.workbench} aria-labelledby="orchestrator-title">
      <header className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>Repository task decomposition · cost router</span>
          <h1 id="orchestrator-title">仓库任务编排预检</h1>
          <p>在创建任何运行之前，锁定模型选择、检查风险下限，并说明 DAG、成本与证据的真实就绪度。</p>
        </div>
        <div className={styles.boundary} aria-label="执行边界">
          <span>Planning only</span>
          <strong>无 Provider 调用 · 无 Run · 无 SCM 副作用</strong>
          <small>外部执行 NOT_RUN · 认证 NOT_CERTIFIED</small>
        </div>
      </header>

      {loading ? <div className={styles.notice} role="status">正在从后端加载唯一模型目录…</div> : null}
      {catalogError ? <div className={styles.error} role="alert">{catalogError}</div> : null}

      {catalog ? (
        <>
          <section className={styles.catalogSection} aria-labelledby="execution-model-heading">
            <div className={styles.sectionHeader}>
              <div>
                <span className={styles.eyebrow}>Immutable selection · {catalog.catalogVersion}</span>
                <h2 id="execution-model-heading">执行模型</h2>
              </div>
              <span className={styles.status} data-tone={statusTone(catalog.status)}>{catalog.status}</span>
            </div>

            {catalog.reasons.length > 0 ? (
              <div className={styles.catalogReasons} role="status">
                <strong>目录尚未就绪</strong>
                <ul>{catalog.reasons.map((reason) => <li key={reason}>{readableReason(reason)}</li>)}</ul>
              </div>
            ) : null}

            <fieldset className={styles.modeFieldset}>
              <legend className="sr-only">选择 Smart 或手动模型模式</legend>
              <label className={`${styles.modeCard} ${mode === "smart" ? styles.selected : ""}`}>
                <input
                  type="radio"
                  name="execution-mode"
                  value="smart"
                  checked={mode === "smart"}
                  onChange={() => {
                    setMode("smart");
                    setSelectedModel(null);
                    setResult(null);
                  }}
                />
                <span className={styles.modeCopy}>
                  <span><strong>Smart — 每个任务的最佳价值</strong><em>推荐</em></span>
                  <small>后端在固定目录内按原子任务、风险下限与成本性能独立路由。</small>
                </span>
              </label>

              <label className={`${styles.modeCard} ${mode === "manual" ? styles.selected : ""}`}>
                <input
                  type="radio"
                  name="execution-mode"
                  value="manual"
                  checked={mode === "manual"}
                  onChange={() => {
                    setMode("manual");
                    setResult(null);
                  }}
                />
                <span className={styles.modeCopy}>
                  <span><strong>手动选择主实现模型</strong><em>严格锁定</em></span>
                  <small>默认不会静默切换；必需的独立验证仍可由系统策略指定。</small>
                </span>
              </label>
            </fieldset>

            <div className={styles.modelGrid} aria-label="后端模型目录">
              {catalog.models.map((model) => (
                <label
                  className={`${styles.modelCard} ${selectedModel === model.alias ? styles.selectedModel : ""}`}
                  key={model.alias}
                  title={model.reasons.map(readableReason).join("; ")}
                >
                  <span className={styles.modelTitle}>
                    <input
                      type="radio"
                      name="manual-model"
                      value={model.alias}
                      disabled={mode !== "manual" || !model.selectable}
                      checked={selectedModel === model.alias}
                      onChange={() => {
                        setSelectedModel(model.alias);
                        setResult(null);
                      }}
                    />
                    <span><strong>{model.displayName}</strong><code>{model.alias}</code></span>
                  </span>
                  <span className={styles.modelMeta}>
                    <span>{model.provider}</span>
                    <span>Cost {model.relativeCostTier}/5</span>
                    <span>{model.highestRoutingTier}</span>
                  </span>
                  <small>{model.roleHint.replaceAll("_", " ")}</small>
                  <span className={styles.unavailable}>{model.status}</span>
                  <ul>
                    {model.reasons.slice(0, 3).map((reason) => <li key={reason}>{readableReason(reason)}</li>)}
                  </ul>
                </label>
              ))}
            </div>

            <div className={styles.policyRow}>
              {mode === "manual" ? (
                <label className={styles.toggle}>
                  <input
                    type="checkbox"
                    checked={fallbackEnabled}
                    onChange={(event) => {
                      setFallbackEnabled(event.target.checked);
                      setResult(null);
                    }}
                  />
                  <span>模型失败时允许 allowlist 内智能 fallback</span>
                </label>
              ) : (
                <div className={styles.routerPolicy}>
                  <strong>Smart 使用服务端 router policy</strong>
                  <span>调用方不能关闭强制风险门、预算硬停止或有界升级策略。</span>
                </div>
              )}
              <label>
                <span>优化策略</span>
                <select
                  value={optimizationProfile}
                  onChange={(event) => setOptimizationProfile(event.target.value as RepositoryPreflightRequest["optimizationProfile"])}
                >
                  {catalog.optimizationProfiles.map((profile) => <option key={profile}>{profile}</option>)}
                </select>
              </label>
              <label>
                <span>验证策略</span>
                <select
                  value={verificationPolicy}
                  onChange={(event) => setVerificationPolicy(event.target.value as RepositoryPreflightRequest["verificationPolicy"])}
                >
                  {catalog.verificationPolicies.map((policy) => <option key={policy}>{policy}</option>)}
                </select>
              </label>
            </div>
          </section>

          <section className={styles.riskSection} aria-labelledby="risk-heading">
            <div className={styles.sectionHeader}>
              <div><span className={styles.eyebrow}>Risk gates before ranking</span><h2 id="risk-heading">风险下限</h2></div>
              <small>高风险至少 L3；长周期任务至少 L4。</small>
            </div>
            <div className={styles.riskGrid}>
              {([
                ["security", "安全"],
                ["dataMigration", "数据迁移"],
                ["concurrency", "并发"],
                ["publicContract", "公共契约"],
                ["blastRadius", "爆炸半径"],
              ] as const).map(([field, label]) => (
                <label key={field}>
                  <span>{label}</span>
                  <select value={risk[field]} onChange={(event) => updateRisk(field, event.target.value as RepositoryRiskLevel)}>
                    {riskOptions.map((level) => <option key={level}>{level}</option>)}
                  </select>
                </label>
              ))}
              <label className={styles.longHorizon}>
                <input
                  type="checkbox"
                  checked={risk.longHorizon}
                  onChange={(event) => {
                    setRisk((current) => ({ ...current, longHorizon: event.target.checked }));
                    setResult(null);
                  }}
                />
                <span>长周期迁移 / long horizon</span>
              </label>
            </div>
            <div className={styles.preflightAction}>
              <p>
                {mode === "manual" && !selectedDescriptor?.selectable
                  ? "所有目录项当前均未配置，无法锁定手动模型；可使用 Smart 验证阻断原因。"
                  : "预检仅验证选择、风险与配置，不会创建任务或调用模型。"}
              </p>
              <button type="button" onClick={() => void submitPreflight()} disabled={!canPreflight}>
                {submitting ? "预检中…" : "运行保守预检"}
              </button>
            </div>
            {preflightError ? <div className={styles.error} role="alert">{preflightError}</div> : null}
          </section>

          {result ? (
            <section className={styles.resultSection} aria-labelledby="preflight-result-heading" aria-live="polite">
              <div className={styles.sectionHeader}>
                <div><span className={styles.eyebrow}>Preflight decision</span><h2 id="preflight-result-heading">预检结果</h2></div>
                <span className={styles.status} data-tone={statusTone(result.status)}>{result.status}</span>
              </div>
              <div className={styles.readinessGrid}>
                <article>
                  <span>模型配置</span><strong>{result.configurationStatus}</strong>
                  <small>风险下限 {result.minimumRoutingTier} · resolved {result.resolvedModel ?? "none"}</small>
                </article>
                <article>
                  <span>任务 DAG</span><strong>{result.dag.status}</strong>
                  <small>{result.dag.tasks.length} tasks · {result.dag.waves.length} waves</small>
                </article>
                <article>
                  <span>成本估算</span><strong>{result.cost.status}</strong>
                  <small>{result.cost.estimatedRunCost === null ? "未产生估算" : `${result.cost.currency} ${result.cost.estimatedRunCost}`}</small>
                </article>
                <article>
                  <span>认证</span><strong>{result.evidence.certification}</strong>
                  <small>external {result.evidence.externalVerification}</small>
                </article>
              </div>

              <div className={styles.resultColumns}>
                <article>
                  <h3>阻断与配置原因</h3>
                  <ul>{result.reasons.map((reason) => <li key={reason}>{readableReason(reason)}</li>)}</ul>
                  <p>{result.cost.reason}</p>
                </article>
                <article>
                  <h3>DAG 就绪度</h3>
                  <ol>{result.dag.requiredStages.map((stage) => <li key={stage}>{readableReason(stage)}</li>)}</ol>
                  <p>{result.dag.reason}</p>
                </article>
                <article>
                  <h3>不可变选择与审计解释</h3>
                  {result.selection ? <code className={styles.digest}>{result.selection.digest}</code> : null}
                  <ul>{result.auditExplanation.map((item) => <li key={item}>{item}</li>)}</ul>
                </article>
              </div>

              <div className={styles.evidenceStrip} aria-label="副作用与证据状态">
                {Object.entries(result.evidence).map(([key, value]) => (
                  <span key={key}><small>{key}</small><strong>{value}</strong></span>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
