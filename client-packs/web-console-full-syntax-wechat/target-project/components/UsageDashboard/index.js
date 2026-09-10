// Top-level helpers and constants
try { var emptyCredentials = { tenantId: "", actorId: "", token: "" }; } catch(e) {}
try { var alertThresholds = [5000, 8000, 9500, 10000]; } catch(e) {}
try { var percent = function percent(usageBps) {
    return `${(usageBps / 100).toFixed(2)}%`;
} } catch(e) {}
try { var localTime = function localTime(value) {
    return new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "medium",
    }).format(new Date(value));
} } catch(e) {}
try { var localDate = function localDate(value) {
    return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(value));
} } catch(e) {}
try { var requestHeaders = function requestHeaders(session) {
    if (session.kind === "account")
        return {};
    return {
        "Authorization": `Bearer ${session.credentials.token}`,
        "X-ELMOS-Tenant": session.credentials.tenantId,
        "X-ELMOS-Actor": session.credentials.actorId,
    };
} } catch(e) {}
try { var meterLabel = function meterLabel(label, consumed, limit, usageBps) {
    return `${label}：已使用 ${formatQuota(consumed)}，额度 ${formatQuota(limit)}，消耗进度 ${percent(usageBps)}`;
} } catch(e) {}
try { var parseHistory = function parseHistory(value) {
    if (typeof value !== "object" || value === null || !("items" in value)
        || !Array.isArray(value.items)) {
        throw new Error("USAGE_HISTORY_CONTRACT_INVALID");
    }
    return value.items;
} } catch(e) {}
try { var parsePreference = function parsePreference(value) {
    if (typeof value !== "object" || value === null
        || !Array.isArray(value.thresholdBps)) {
        throw new Error("USAGE_ALERT_CONTRACT_INVALID");
    }
    return value;
} } catch(e) {}
try { var parseEvents = function parseEvents(value) {
    if (typeof value !== "object" || value === null || !("items" in value)
        || !Array.isArray(value.items)) {
        throw new Error("USAGE_EVENTS_CONTRACT_INVALID");
    }
    return value.items;
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    allowLocalCredentials: {
      type: null,
      value: false,
    },
    emailAlertsEnabled: {
      type: null,
      value: false,
    },
  },
  data: {
    form: "emptyCredentials",
    session: "allowLocalCredentials ? null : { kind: \"account\" }",
    readState: "allowLocalCredentials ? { kind: \"idle\" } : { kind: \"loading\" }",
    insights: "{ kind: \"idle\" }",
    savingAlerts: false,
    exportQuery: null,
    forecast: null,
  },
  lifetimes: {
    attached() {
      const setForm = (val) => { this.setData({ form: typeof val === "function" ? val(this.data.form) : val }); };
      const setSession = (val) => { this.setData({ session: typeof val === "function" ? val(this.data.session) : val }); };
      const setReadState = (val) => { this.setData({ readState: typeof val === "function" ? val(this.data.readState) : val }); };
      const setInsights = (val) => { this.setData({ insights: typeof val === "function" ? val(this.data.insights) : val }); };
      const setSavingAlerts = (val) => { this.setData({ savingAlerts: typeof val === "function" ? val(this.data.savingAlerts) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          if (!session)
        return;
    let disposed = false;
    let stopped = false;
    let timer;
    let controller;
    let lastSnapshot = null;
    const schedule = (seconds) => {
        if (disposed)
            return;
        window.clearTimeout(timer);
        timer = window.setTimeout(() => void refresh(), seconds * 1_000);
    };
    const refresh = async () => {
        if (disposed || stopped)
            return;
        if (document.visibilityState === "hidden") {
            schedule(5);
            return;
        }
        controller?.abort();
        controller = new AbortController();
        if (!lastSnapshot)
            setReadState({ kind: "loading" });
        try {
            const response = await fetch("/api/usage/current", {
                method: "GET",
                cache: "no-store",
                headers: requestHeaders(session),
                signal: controller.signal,
            });
            const body = await response.json();
            if (!response.ok) {
                const error = parseUsageApiError(body, response.status);
                if (response.status === 401 || response.status === 403 || !error.retryable) {
                    stopped = true;
                    setReadState(lastSnapshot
                        ? { kind: "stale", snapshot: lastSnapshot, error }
                        : { kind: "error", error });
                    return;
                }
                setReadState(lastSnapshot
                    ? { kind: "stale", snapshot: lastSnapshot, error }
                    : { kind: "error", error });
                schedule(5);
                return;
            }
            let snapshot;
            try {
                snapshot = parseCurrentUsageSnapshot(body);
            }
            catch {
                stopped = true;
                const contractError = {
                    code: "USAGE_RESPONSE_CONTRACT_INVALID",
                    message: "实时计量响应不符合当前客户端契约，已停止自动刷新。",
                    retryable: false,
                    status: "ERROR",
                };
                setReadState(lastSnapshot
                    ? { kind: "stale", snapshot: lastSnapshot, error: contractError }
                    : { kind: "error", error: contractError });
                return;
            }
            lastSnapshot = snapshot;
            setReadState({ kind: "current", snapshot });
            schedule(Math.max(2, snapshot.refreshAfterSeconds));
        }
        catch (error) {
            if (error instanceof DOMException && error.name === "AbortError")
                return;
            const transportError = {
                code: "USAGE_TRANSPORT_ERROR",
                message: "暂时无法连接实时计量服务；已保留最近一次可信读数。",
                retryable: true,
                status: "ERROR",
            };
            setReadState(lastSnapshot
                ? { kind: "stale", snapshot: lastSnapshot, error: transportError }
                : { kind: "error", error: transportError });
            schedule(5);
        }
    };
    const onVisibilityChange = () => {
        if (document.visibilityState === "visible") {
            window.clearTimeout(timer);
            void refresh();
        }
        else {
            controller?.abort();
        }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    void refresh();
    return () => {
        disposed = true;
        window.clearTimeout(timer);
        controller?.abort();
        document.removeEventListener("visibilitychange", onVisibilityChange);
    };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          if (!session || session.kind !== "account")
        return;
    let disposed = false;
    const load = async () => {
        setInsights({ kind: "loading" });
        const to = new Date();
        const from = new Date(to.getTime() - 30 * 24 * 60 * 60 * 1_000);
        const query = new URLSearchParams({
            from: from.toISOString(),
            to: to.toISOString(),
            bucket: "DAY",
        });
        const eventsQuery = new URLSearchParams({
            from: from.toISOString(),
            to: to.toISOString(),
            scope: "SELF",
            limit: "100",
            offset: "0",
        });
        try {
            const [historyResponse, eventsResponse, alertResponse] = await Promise.all([
                fetch(`/api/usage/history?${query}`, { cache: "no-store" }),
                fetch(`/api/usage/events?${eventsQuery}`, { cache: "no-store" }),
                fetch("/api/usage/alerts", { cache: "no-store" }),
            ]);
            const [historyBody, eventsBody, alertBody] = await Promise.all([
                historyResponse.json(),
                eventsResponse.json(),
                alertResponse.json(),
            ]);
            if (!historyResponse.ok || !eventsResponse.ok || !alertResponse.ok) {
                throw new Error("USAGE_INSIGHTS_UNAVAILABLE");
            }
            if (!disposed) {
                setInsights({
                    kind: "ready",
                    history: parseHistory(historyBody),
                    events: parseEvents(eventsBody),
                    preference: parsePreference(alertBody),
                });
            }
        }
        catch {
            if (!disposed)
                setInsights({ kind: "error", message: "历史明细与提醒设置暂不可用。" });
        }
    };
    void load();
    return () => { disposed = true; };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
  },
});
