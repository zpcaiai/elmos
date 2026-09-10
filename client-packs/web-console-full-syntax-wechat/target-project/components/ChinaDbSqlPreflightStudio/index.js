// Top-level helpers and constants
try { const targetPresets = {
    dm8: {
        targetVersion: "8.1.3.140",
        targetEdition: "enterprise",
        compatibilityMode: "oracle-compatible-explicit",
        targetDriver: "dmjdbc-8.1.3.140",
        targetCharset: "UTF-8",
        targetCollation: "BINARY",
        targetTimeZone: "Asia/Shanghai",
    },
    kingbasees: {
        targetVersion: "V8R6",
        targetEdition: "enterprise",
        compatibilityMode: "oracle-compatible",
        targetDriver: "kingbase8-8.6.0",
        targetCharset: "UTF-8",
        targetCollation: "zh_CN.UTF-8",
        targetTimeZone: "Asia/Shanghai",
    },
    opengauss: {
        targetVersion: "6.0.0",
        targetEdition: "enterprise",
        compatibilityMode: "A",
        targetDriver: "opengauss-jdbc-6.0.0",
        targetCharset: "UTF-8",
        targetCollation: "en_US.UTF-8",
        targetTimeZone: "Asia/Shanghai",
    },
    tidb: {
        targetVersion: "8.1.0",
        targetEdition: "community",
        compatibilityMode: "mysql-8.0",
        targetDriver: "mysql-connector-j-8.4.0",
        targetCharset: "utf8mb4",
        targetCollation: "utf8mb4_bin",
        targetTimeZone: "Asia/Shanghai",
    },
    "gbase-8s": {
        targetVersion: "8.8",
        targetEdition: "enterprise",
        compatibilityMode: "oracle-compatible",
        targetDriver: "gbasedbt-jdbc-8.8",
        targetCharset: "UTF-8",
        targetCollation: "zh_CN.UTF-8",
        targetTimeZone: "Asia/Shanghai",
    },
    "gbase-8c": {
        targetVersion: "3.3.0",
        targetEdition: "enterprise",
        compatibilityMode: "postgresql-compatible",
        targetDriver: "gbase8c-jdbc-3.3.0",
        targetCharset: "UTF-8",
        targetCollation: "zh_CN.UTF-8",
        targetTimeZone: "Asia/Shanghai",
    },
    "gbase-8a": {
        targetVersion: "9.5.3",
        targetEdition: "enterprise",
        compatibilityMode: "analytical-gbase",
        targetDriver: "gbase8a-jdbc-9.5.3",
        targetCharset: "UTF-8",
        targetCollation: "utf8_bin",
        targetTimeZone: "Asia/Shanghai",
    },
    "highgo-hgdb": {
        targetVersion: "V6.0",
        targetEdition: "enterprise",
        compatibilityMode: "oracle-compatible",
        targetDriver: "hgdb-jdbc-6.0",
        targetCharset: "UTF-8",
        targetCollation: "zh_CN.UTF-8",
        targetTimeZone: "Asia/Shanghai",
    },
    "oceanbase-oracle": {
        targetVersion: "4.2.1",
        targetEdition: "enterprise",
        compatibilityMode: "oracle",
        targetDriver: "oceanbase-client-2.4.6",
        targetCharset: "UTF-8",
        targetCollation: "BINARY",
        targetTimeZone: "Asia/Shanghai",
    },
    "oceanbase-mysql": {
        targetVersion: "4.2.1",
        targetEdition: "community",
        compatibilityMode: "mysql",
        targetDriver: "oceanbase-client-2.4.6",
        targetCharset: "utf8mb4",
        targetCollation: "utf8mb4_general_ci",
        targetTimeZone: "Asia/Shanghai",
    },
    "gaussdb-oracle": {
        targetVersion: "503.1.0",
        targetEdition: "enterprise",
        compatibilityMode: "ora",
        targetDriver: "gaussdb-jdbc-503.1.0",
        targetCharset: "UTF-8",
        targetCollation: "zh_CN.UTF-8",
        targetTimeZone: "Asia/Shanghai",
    },
    "gaussdb-m": {
        targetVersion: "503.1.0",
        targetEdition: "enterprise",
        compatibilityMode: "m",
        targetDriver: "gaussdb-jdbc-503.1.0",
        targetCharset: "utf8mb4",
        targetCollation: "utf8mb4_general_ci",
        targetTimeZone: "Asia/Shanghai",
    },
    goldendb: {
        targetVersion: "v7.1.0",
        targetEdition: "enterprise",
        compatibilityMode: "oracle-mysql-hybrid",
        targetDriver: "goldendb-jdbc-7.1.0",
        targetCharset: "UTF-8",
        targetCollation: "BINARY",
        targetTimeZone: "Asia/Shanghai",
    },
}; } catch(e) {}
try { const initialFields = {
    queryId: "web-sql-preflight",
    sourceProfile: "oracle-26ai-ee",
    targetId: "dm8",
    ...targetPresets.dm8,
    sql: "SELECT 1 FROM t\n",
}; } catch(e) {}
try { const fieldErrors = {
    ACCOUNT_SESSION_REQUIRED: "请先登录企业账户，再运行 SQL 预检。",
    ACCOUNT_PERMISSION_REQUIRED: "当前账户缺少 SQL 迁移预检权限。",
    CSRF_ORIGIN_REJECTED: "请求未通过同源校验，请刷新页面后重试。",
    CHINADB_SQL_PREFLIGHT_DISABLED: "SQL 预检服务尚未启用。",
    CHINADB_SQL_PREFLIGHT_NOT_CONFIGURED: "SQL 预检服务尚未配置。",
    CHINADB_SQL_LOCAL_RUNNER_UNAVAILABLE: "当前部署未安装已锁定的 SQL 本地运行器（uv / elmos-sql-transpiler）；本次预检未执行。",
    CHINADB_SQL_PREFLIGHT_UNAVAILABLE: "SQL 预检服务当前不可用；本次预检未执行。",
    CHINADB_SQL_UPSTREAM_UNAVAILABLE: "受信 SQL 预检服务当前不可用；本次预检未执行。",
    CHINADB_SQL_CAPABILITY_SNAPSHOT_STALE: "能力目录已更新，请刷新后使用新的能力摘要。",
    CHINADB_SQL_INPUT_TOO_LARGE: "SQL 超过 256 KiB 的交互式预检上限。",
    CHINADB_SQL_PARAMETERS_INVALID: "参数契约超过 256 项或格式无效。",
    CHINADB_SQL_UPSTREAM_TIMEOUT: "预检服务在 15 秒内未返回，请稍后重试。",
    BUSINESS_AUDIT_UNAVAILABLE: "业务审计当前不可用，本次预检未执行。",
}; } catch(e) {}
try { const verificationLabels = {
    sourceParse: "源 SQL 解析",
    targetAdapter: "目标适配器",
    targetEmit: "目标 SQL 发射",
    targetReparse: "目标 SQL 重解析",
    sourceExecution: "源端执行",
    targetExecution: "目标端执行",
    resultEquivalence: "结果等价",
    externalExecution: "外部执行",
}; } catch(e) {}
try { function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
} } catch(e) {}
try { async function responseJson(response) {
    const text = await response.text();
    try {
        return JSON.parse(text);
    }
    catch {
        throw new Error("CHINADB_SQL_RESPONSE_UNPARSEABLE");
    }
} } catch(e) {}
try { function errorMessage(error) {
    if (error instanceof ChinaDbSqlPolicyError) {
        return fieldErrors[error.errorCode] ?? `请求未通过安全校验（${error.errorCode}）。`;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
        return "请求已取消。";
    }
    if (error instanceof Error && error.name === "TimeoutError") {
        return "预检请求超时，请稍后重试。";
    }
    if (error instanceof Error && fieldErrors[error.message])
        return fieldErrors[error.message];
    return "SQL 预检当前不可用；未生成目标 SQL，也未触发外部执行。";
} } catch(e) {}
try { function apiError(payload, fallback) {
    if (!isRecord(payload))
        return new Error(fallback);
    const code = typeof payload.errorCode === "string" ? payload.errorCode : fallback;
    return new Error(code);
} } catch(e) {}
try { async function sha256Text(value) {
    const bytes = new TextEncoder().encode(value);
    const hashed = await crypto.subtle.digest("SHA-256", bytes);
    return `sha256:${Array.from(new Uint8Array(hashed), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    capabilities: null,
    fields: "initialFields",
    parameters: [],
    result: null,
    loadingCapabilities: true,
    busy: false,
    error: "",
    errorSummary: {"current":null},
    resultPanel: {"current":null},
    activeAssessment: {"current":null},
    selectedTarget: null,
  },
  lifetimes: {
    attached() {
      const setCapabilities = (val) => { this.setData({ capabilities: typeof val === "function" ? val(this.data.capabilities) : val }); };
      const setFields = (val) => { this.setData({ fields: typeof val === "function" ? val(this.data.fields) : val }); };
      const setParameters = (val) => { this.setData({ parameters: typeof val === "function" ? val(this.data.parameters) : val }); };
      const setResult = (val) => { this.setData({ result: typeof val === "function" ? val(this.data.result) : val }); };
      const setLoadingCapabilities = (val) => { this.setData({ loadingCapabilities: typeof val === "function" ? val(this.data.loadingCapabilities) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
      const setError = (val) => { this.setData({ error: typeof val === "function" ? val(this.data.error) : val }); };
      const errorSummary = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const resultPanel = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeAssessment = { current: { focus: () => {}, scrollIntoView: () => {} } };
      // Lifecycle effect effect_0
      (async () => {
        try {
          const controller = new AbortController();
    async function loadCapabilities() {
        try {
            const response = await fetch("/api/capabilities/database-sql", {
                cache: "no-store",
                signal: controller.signal,
            });
            const payload = await responseJson(response);
            if (!response.ok)
                throw apiError(payload, "CHINADB_SQL_CAPABILITIES_UNAVAILABLE");
            const parsed = parseChinaDbSqlCapabilities(payload);
            setCapabilities(parsed);
            setFields((current) => ({
                ...current,
                targetId: parsed.targets.some((target) => target.id === current.targetId)
                    ? current.targetId
                    : parsed.targets[0].id,
            }));
        }
        catch (loadError) {
            if (controller.signal.aborted)
                return;
            setError(errorMessage(loadError));
            requestAnimationFrame(() => errorSummary.current?.focus());
        }
        finally {
            if (!controller.signal.aborted)
                setLoadingCapabilities(false);
        }
    }
    void loadCapabilities();
    return () => controller.abort();
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    updateField(key, value) {
      const errorSummary = this.data.errorSummary || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const resultPanel = this.data.resultPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeAssessment = this.data.activeAssessment || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (key === "targetId" && typeof value === "string" && targetPresets[value]) {
        setFields((current) => ({
            ...current,
            targetId: value,
            ...targetPresets[value],
        }));
    }
    else {
        setFields((current) => ({ ...current, [key]: value }));
    }
    setResult(null);
      } catch (err) {
        console.warn("updateField execution warning:", err);
      }
    },
    addParameter() {
      const errorSummary = this.data.errorSummary || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const resultPanel = this.data.resultPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeAssessment = this.data.activeAssessment || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (parameters.length >= chinaDbSqlParameterLimit)
        return;
    setParameters((current) => [...current, { name: "", logicalType: "", nullable: false }]);
    setResult(null);
      } catch (err) {
        console.warn("addParameter execution warning:", err);
      }
    },
    updateParameter(index, patch) {
      const errorSummary = this.data.errorSummary || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const resultPanel = this.data.resultPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeAssessment = this.data.activeAssessment || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setParameters((current) => current.map((parameter, parameterIndex) => (parameterIndex === index ? { ...parameter, ...patch } : parameter)));
    setResult(null);
      } catch (err) {
        console.warn("updateParameter execution warning:", err);
      }
    },
    removeParameter(index) {
      const errorSummary = this.data.errorSummary || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const resultPanel = this.data.resultPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeAssessment = this.data.activeAssessment || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setParameters((current) => current.filter((_, parameterIndex) => parameterIndex !== index));
    setResult(null);
      } catch (err) {
        console.warn("removeParameter execution warning:", err);
      }
    },
    async submit(event) {
      const errorSummary = this.data.errorSummary || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const resultPanel = this.data.resultPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeAssessment = this.data.activeAssessment || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        event.preventDefault();
    if (!capabilities || busy)
        return;
    setBusy(true);
    setError("");
    setResult(null);
    const controller = new AbortController();
    activeAssessment.current = controller;
    let timedOut = false;
    const timeout = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
    }, 17_000);
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
        if (!response.ok)
            throw apiError(payload, "CHINADB_SQL_PREFLIGHT_REJECTED");
        const sourceDigest = await sha256Text(request.sql);
        const parsed = parseChinaDbSqlPreflightResult(payload, request, capabilities, sourceDigest);
        setResult(parsed);
        requestAnimationFrame(() => resultPanel.current?.focus());
    }
    catch (submitError) {
        setError(timedOut ? "预检请求超时，请稍后重试。" : errorMessage(submitError));
        requestAnimationFrame(() => errorSummary.current?.focus());
    }
    finally {
        window.clearTimeout(timeout);
        if (activeAssessment.current === controller)
            activeAssessment.current = null;
        setBusy(false);
    }
      } catch (err) {
        console.warn("submit execution warning:", err);
      }
    },
    cancelAssessment() {
      const errorSummary = this.data.errorSummary || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const resultPanel = this.data.resultPanel || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeAssessment = this.data.activeAssessment || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        activeAssessment.current?.abort();
      } catch (err) {
        console.warn("cancelAssessment execution warning:", err);
      }
    },
  },
});
