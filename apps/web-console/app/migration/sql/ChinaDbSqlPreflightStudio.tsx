"use client";

import Link from "next/link";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { Icon } from "../../components/Icon";
import { StatusChip } from "../../components/StatusChip";
import {
  bindChinaDbSqlRequestToCapabilities,
  ChinaDbSqlPolicyError,
  chinaDbSqlInputLimitBytes,
  chinaDbSqlParameterLimit,
  chinaDbSqlSourceProfiles,
  parseChinaDbSqlCapabilities,
  parseChinaDbSqlPreflightRequest,
  parseChinaDbSqlPreflightResult,
  type ChinaDbSqlCapabilities,
  type ChinaDbSqlParameter,
  type ChinaDbSqlPreflightRequest,
  type ChinaDbSqlPreflightResult,
} from "../../lib/chinadbSqlContracts";
import styles from "./ChinaDbSqlPreflightStudio.module.css";

type FormFields = Omit<ChinaDbSqlPreflightRequest, "schemaVersion" | "capabilitySnapshotDigest" | "parameters">;

const initialFields: FormFields = {
  queryId: "web-sql-preflight",
  sourceProfile: "oracle-26ai-ee",
  targetId: "dm8",
  targetVersion: "",
  targetEdition: "",
  compatibilityMode: "",
  targetDriver: "",
  targetCharset: "",
  targetCollation: "",
  targetTimeZone: "",
  sql: "",
};

const fieldErrors: Record<string, string> = {
  ACCOUNT_SESSION_REQUIRED: "请先登录企业账户，再运行 SQL 预检。",
  ACCOUNT_PERMISSION_REQUIRED: "当前账户缺少 SQL 迁移预检权限。",
  CSRF_ORIGIN_REJECTED: "请求未通过同源校验，请刷新页面后重试。",
  CHINADB_SQL_PREFLIGHT_DISABLED: "SQL 预检服务尚未启用。",
  CHINADB_SQL_PREFLIGHT_NOT_CONFIGURED: "SQL 预检服务尚未配置。",
  CHINADB_SQL_CAPABILITY_SNAPSHOT_STALE: "能力目录已更新，请刷新后使用新的能力摘要。",
  CHINADB_SQL_INPUT_TOO_LARGE: "SQL 超过 256 KiB 的交互式预检上限。",
  CHINADB_SQL_PARAMETERS_INVALID: "参数契约超过 256 项或格式无效。",
  CHINADB_SQL_UPSTREAM_TIMEOUT: "预检服务在 15 秒内未返回，请稍后重试。",
  BUSINESS_AUDIT_UNAVAILABLE: "业务审计当前不可用，本次预检未执行。",
};

const verificationLabels: Record<keyof ChinaDbSqlPreflightResult["verification"], string> = {
  sourceParse: "源 SQL 解析",
  targetAdapter: "目标适配器",
  targetEmit: "目标 SQL 发射",
  targetReparse: "目标 SQL 重解析",
  sourceExecution: "源端执行",
  targetExecution: "目标端执行",
  resultEquivalence: "结果等价",
  externalExecution: "外部执行",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function responseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new Error("CHINADB_SQL_RESPONSE_UNPARSEABLE");
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof ChinaDbSqlPolicyError) {
    return fieldErrors[error.errorCode] ?? `请求未通过安全校验（${error.errorCode}）。`;
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "请求已取消。";
  }
  if (error instanceof Error && error.name === "TimeoutError") {
    return "预检请求超时，请稍后重试。";
  }
  if (error instanceof Error && fieldErrors[error.message]) return fieldErrors[error.message];
  return "SQL 预检当前不可用；未生成目标 SQL，也未触发外部执行。";
}

function apiError(payload: unknown, fallback: string): Error {
  if (!isRecord(payload)) return new Error(fallback);
  const code = typeof payload.errorCode === "string" ? payload.errorCode : fallback;
  return new Error(code);
}

async function sha256Text(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const hashed = await crypto.subtle.digest("SHA-256", bytes);
  return `sha256:${Array.from(new Uint8Array(hashed), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

export function ChinaDbSqlPreflightStudio() {
  const [capabilities, setCapabilities] = useState<ChinaDbSqlCapabilities | null>(null);
  const [fields, setFields] = useState<FormFields>(initialFields);
  const [parameters, setParameters] = useState<ChinaDbSqlParameter[]>([]);
  const [result, setResult] = useState<ChinaDbSqlPreflightResult | null>(null);
  const [loadingCapabilities, setLoadingCapabilities] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const errorSummary = useRef<HTMLDivElement>(null);
  const resultPanel = useRef<HTMLElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function loadCapabilities() {
      try {
        const response = await fetch("/api/capabilities/database-sql", {
          cache: "no-store",
          signal: controller.signal,
        });
        const payload = await responseJson(response);
        if (!response.ok) throw apiError(payload, "CHINADB_SQL_CAPABILITIES_UNAVAILABLE");
        const parsed = parseChinaDbSqlCapabilities(payload);
        setCapabilities(parsed);
        setFields((current) => ({
          ...current,
          targetId: parsed.targets.some((target) => target.id === current.targetId)
            ? current.targetId
            : parsed.targets[0].id,
        }));
      } catch (loadError) {
        if (controller.signal.aborted) return;
        setError(errorMessage(loadError));
        requestAnimationFrame(() => errorSummary.current?.focus());
      } finally {
        if (!controller.signal.aborted) setLoadingCapabilities(false);
      }
    }
    void loadCapabilities();
    return () => controller.abort();
  }, []);

  const selectedTarget = useMemo(
    () => capabilities?.targets.find((target) => target.id === fields.targetId) ?? null,
    [capabilities, fields.targetId],
  );

  function updateField<Key extends keyof FormFields>(key: Key, value: FormFields[Key]) {
    setFields((current) => ({ ...current, [key]: value }));
    setResult(null);
  }

  function addParameter() {
    if (parameters.length >= chinaDbSqlParameterLimit) return;
    setParameters((current) => [...current, { name: "", logicalType: "", nullable: false }]);
    setResult(null);
  }

  function updateParameter(index: number, patch: Partial<ChinaDbSqlParameter>) {
    setParameters((current) => current.map((parameter, parameterIndex) => (
      parameterIndex === index ? { ...parameter, ...patch } : parameter
    )));
    setResult(null);
  }

  function removeParameter(index: number) {
    setParameters((current) => current.filter((_, parameterIndex) => parameterIndex !== index));
    setResult(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!capabilities || busy) return;
    setBusy(true);
    setError("");
    setResult(null);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 17_000);
    try {
      const request = parseChinaDbSqlPreflightRequest({
        schemaVersion: "1.0",
        ...fields,
        capabilitySnapshotDigest: capabilities.capabilitySnapshotDigest,
        parameters,
      });
      bindChinaDbSqlRequestToCapabilities(request, capabilities);
      const response = await fetch("/api/database-sql/preflight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        cache: "no-store",
        signal: controller.signal,
      });
      const payload = await responseJson(response);
      if (!response.ok) throw apiError(payload, "CHINADB_SQL_PREFLIGHT_REJECTED");
      const sourceDigest = await sha256Text(request.sql);
      const parsed = parseChinaDbSqlPreflightResult(
        payload,
        request,
        capabilities,
        sourceDigest,
      );
      setResult(parsed);
      requestAnimationFrame(() => resultPanel.current?.focus());
    } catch (submitError) {
      setError(errorMessage(submitError));
      requestAnimationFrame(() => errorSummary.current?.focus());
    } finally {
      window.clearTimeout(timeout);
      setBusy(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="page-header">
        <div>
          <span className="overline">BATCH 31 · READ-ONLY SOURCE PREFLIGHT</span>
          <h1>ChinaDB SQL 只读预检</h1>
          <p>解析精确源方言并列出迁移义务；目标适配器、目标 SQL、实库执行与认证始终失败关闭。</p>
        </div>
        <Link className="button button-secondary" href="/migration">
          <Icon name="arrow" size={16} />返回迁移工坊
        </Link>
      </section>

      <section className="source-notice" role="status" aria-live="polite">
        <Icon name={capabilities ? "check" : "clock"} size={16} />
        <span>
          {loadingCapabilities
            ? "正在读取受保护的 control-plane 能力快照…"
            : capabilities
              ? `已绑定 ${capabilities.targetCount} 个目标、${capabilities.plannedRouteCount} 条规划路线；不会连接数据库。`
              : "能力服务不可用；提交保持禁用。"}
        </span>
        <StatusChip status={capabilities ? "SPEC_ONLY" : "BLOCKED"} compact />
      </section>

      {error && (
        <div ref={errorSummary} className={styles.errorSummary} role="alert" tabIndex={-1}>
          <Icon name="lock" size={18} />
          <div><strong>预检未执行</strong><p>{error}</p></div>
        </div>
      )}

      <div className={styles.workspace}>
        <form className={`surface-card ${styles.form}`} onSubmit={submit} data-telemetry-ignore="true">
          <div className={styles.sectionHeading}>
            <div><span className="overline">EXACT REQUEST</span><h2>源 SQL 与目标精确元组</h2></div>
            <StatusChip status="BLOCKED" compact />
          </div>

          <fieldset className={styles.fieldset}>
            <legend>源查询身份</legend>
            <div className={styles.gridTwo}>
              <label htmlFor="sql-query-id"><span>Query ID</span><input id="sql-query-id" value={fields.queryId} onChange={(event) => updateField("queryId", event.target.value)} maxLength={160} required autoComplete="off" /></label>
              <label htmlFor="sql-source-profile"><span>精确源 Profile</span><select id="sql-source-profile" value={fields.sourceProfile} onChange={(event) => updateField("sourceProfile", event.target.value as FormFields["sourceProfile"])}>{chinaDbSqlSourceProfiles.map((profile) => <option value={profile} key={profile}>{profile}</option>)}</select></label>
            </div>
          </fieldset>

          <fieldset className={styles.fieldset}>
            <legend>目标精确元组</legend>
            <div className={styles.gridTwo}>
              <label htmlFor="sql-target-id"><span>ChinaDB 目标</span><select id="sql-target-id" value={fields.targetId} onChange={(event) => updateField("targetId", event.target.value as FormFields["targetId"])} disabled={!capabilities}>{capabilities?.targets.map((target) => <option value={target.id} key={target.id}>{target.label} · {target.id}</option>) ?? <option value="dm8">等待能力快照</option>}</select></label>
              <label htmlFor="sql-target-version"><span>精确版本</span><input id="sql-target-version" value={fields.targetVersion} onChange={(event) => updateField("targetVersion", event.target.value)} maxLength={128} placeholder="例如 8.1.3.140" required autoComplete="off" /></label>
              <label htmlFor="sql-target-edition"><span>Edition</span><input id="sql-target-edition" value={fields.targetEdition} onChange={(event) => updateField("targetEdition", event.target.value)} maxLength={128} placeholder="例如 enterprise" required autoComplete="off" /></label>
              <label htmlFor="sql-compatibility-mode"><span>Compatibility mode</span><input id="sql-compatibility-mode" value={fields.compatibilityMode} onChange={(event) => updateField("compatibilityMode", event.target.value)} maxLength={128} placeholder="例如 oracle-compatible-explicit" required autoComplete="off" /></label>
              <label htmlFor="sql-target-driver"><span>Driver</span><input id="sql-target-driver" value={fields.targetDriver} onChange={(event) => updateField("targetDriver", event.target.value)} maxLength={128} placeholder="精确驱动与版本" required autoComplete="off" /></label>
              <label htmlFor="sql-target-charset"><span>Charset</span><input id="sql-target-charset" value={fields.targetCharset} onChange={(event) => updateField("targetCharset", event.target.value)} maxLength={128} placeholder="例如 UTF-8" required autoComplete="off" /></label>
              <label htmlFor="sql-target-collation"><span>Collation</span><input id="sql-target-collation" value={fields.targetCollation} onChange={(event) => updateField("targetCollation", event.target.value)} maxLength={128} placeholder="例如 BINARY" required autoComplete="off" /></label>
              <label htmlFor="sql-target-timezone"><span>Time zone</span><input id="sql-target-timezone" value={fields.targetTimeZone} onChange={(event) => updateField("targetTimeZone", event.target.value)} maxLength={128} placeholder="例如 Asia/Shanghai" required autoComplete="off" /></label>
            </div>
            {selectedTarget && <div className={styles.requirement}><Icon name="database" size={16} /><span><strong>{selectedTarget.label}</strong>{selectedTarget.versionRequirement}；{selectedTarget.compatibilityModeRequirement}</span></div>}
          </fieldset>

          <fieldset className={styles.fieldset}>
            <legend>参数契约</legend>
            <div className={styles.parameterToolbar}><p>仅声明名称、逻辑类型与 nullability；最多 {chinaDbSqlParameterLimit} 项。</p><button type="button" className="button button-secondary" onClick={addParameter} disabled={parameters.length >= chinaDbSqlParameterLimit}><Icon name="plus" size={15} />添加参数</button></div>
            {parameters.length === 0 ? <p className={styles.emptyParameters}>当前请求使用空参数契约。</p> : <div className={styles.parameterList}>{parameters.map((parameter, index) => <div className={styles.parameterRow} key={`parameter-${index}`}>
              <label htmlFor={`sql-parameter-name-${index}`}><span>名称</span><input id={`sql-parameter-name-${index}`} value={parameter.name} onChange={(event) => updateParameter(index, { name: event.target.value })} maxLength={128} required autoComplete="off" /></label>
              <label htmlFor={`sql-parameter-type-${index}`}><span>逻辑类型</span><input id={`sql-parameter-type-${index}`} value={parameter.logicalType} onChange={(event) => updateParameter(index, { logicalType: event.target.value })} maxLength={128} required autoComplete="off" /></label>
              <label className={styles.checkbox} htmlFor={`sql-parameter-nullable-${index}`}><input id={`sql-parameter-nullable-${index}`} type="checkbox" checked={parameter.nullable} onChange={(event) => updateParameter(index, { nullable: event.target.checked })} /><span>Nullable</span></label>
              <button type="button" className="icon-button bordered" onClick={() => removeParameter(index)} aria-label={`删除参数 ${index + 1}`}><Icon name="close" size={14} /></button>
            </div>)}</div>}
          </fieldset>

          <label className={styles.sqlField} htmlFor="sql-source"><span>源 SQL</span><textarea id="sql-source" value={fields.sql} onChange={(event) => updateField("sql", event.target.value)} placeholder="粘贴已脱敏的查询；不要包含凭据、个人信息或未授权生产数据。" required spellCheck={false} /><small>UTF-8 最大 {chinaDbSqlInputLimitBytes / 1024} KiB。SQL 只发送到同源 BFF 和受信 control-plane，不保存为草稿。</small></label>

          <div className={styles.digestBlock}><span>能力快照摘要</span><code>{capabilities?.capabilitySnapshotDigest ?? "尚未绑定"}</code></div>
          <div className={styles.boundary}><Icon name="shield" size={17} /><p>本操作只解析源 SQL。不会生成目标 SQL、连接数据库、执行查询、验证等价性或签发认证。</p></div>
          <div className={styles.actions}><button className="button button-primary" type="submit" disabled={!capabilities || busy}>{busy ? "正在只读解析…" : "运行只读预检"}</button></div>
        </form>

        <aside className={`surface-card ${styles.boundaryCard}`}>
          <span className="overline">FAIL-CLOSED BOUNDARY</span>
          <h2>当前能力上限</h2>
          <dl>
            <div><dt>目标 Renderer</dt><dd>0</dd></div>
            <div><dt>生产数据库访问</dt><dd>FALSE</dd></div>
            <div><dt>目标 SQL</dt><dd>PROHIBITED</dd></div>
            <div><dt>外部执行</dt><dd>NOT_RUN</dd></div>
            <div><dt>认证</dt><dd>NOT_CERTIFIED</dd></div>
          </dl>
          <p>{capabilities?.boundaries.claim ?? "等待受保护能力快照。"}</p>
        </aside>
      </div>

      {result && (
        <section ref={resultPanel} className={`surface-card ${styles.result}`} tabIndex={-1} aria-labelledby="sql-preflight-result-title">
          <div className={styles.resultHeading}>
            <div><span className="overline">TYPED SOURCE ASSESSMENT</span><h2 id="sql-preflight-result-title">预检结果：已阻断</h2><p>{result.routeId} · {result.queryId}</p></div>
            <StatusChip status={result.state} />
          </div>

          <div className={styles.resultFacts}>
            <div><span>源解析</span><StatusChip status={result.verification.sourceParse} compact /></div>
            <div><span>目标 SQL</span><strong>NULL · 未生成</strong></div>
            <div><span>目标状态</span><StatusChip status={result.target.implementationStatus} compact /></div>
            <div><span>认证</span><StatusChip status={result.certification} compact /></div>
          </div>

          <div className={styles.resultGrid}>
            <div>
              <h3>Blockers</h3>
              <div className={styles.blockerList}>{result.blockers.map((blocker, index) => <article className={styles.blocker} key={`${blocker.code}-${index}`}>
                <div><StatusChip status={blocker.severity === "ERROR" ? "BLOCKED" : "REVIEW"} compact /><code>{blocker.code}</code></div>
                <p>{blocker.message}</p>
                <small>{blocker.statementIndex === null ? "全局阻断" : `Statement ${blocker.statementIndex}`}</small>
              </article>)}</div>
            </div>
            <div>
              <h3>Verification</h3>
              <dl className={styles.verification}>{(Object.entries(result.verification) as Array<[keyof typeof result.verification, string]>).map(([key, value]) => <div key={key}><dt>{verificationLabels[key]}</dt><dd><StatusChip status={value} compact /></dd></div>)}</dl>
            </div>
          </div>

          <div className={styles.statementSection}>
            <h3>Typed AST 与语义义务</h3>
            {result.statements.length === 0 ? <p className={styles.noStatements}>源解析失败，没有生成 typed AST。</p> : result.statements.map((statement) => <article className={styles.statement} key={statement.index}>
              <div className={styles.statementHeading}><span>Statement {statement.index}</span><strong>{statement.kind}</strong></div>
              <div className={styles.obligations}>{statement.obligations.map((obligation) => <code key={obligation}>{obligation}</code>)}</div>
              <details><summary>查看 typed source AST</summary><pre>{JSON.stringify(statement.sourceAst, null, 2)}</pre></details>
            </article>)}
          </div>
        </section>
      )}
    </div>
  );
}
