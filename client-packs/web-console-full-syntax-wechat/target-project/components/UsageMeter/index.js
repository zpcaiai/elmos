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
    label: {
      type: null,
      value: null,
    },
    unit: {
      type: null,
      value: null,
    },
    measure: {
      type: null,
      value: null,
    },
  },
  data: {
  },
  lifetimes: {
    attached() {
    },
    detached() {
    },
  },
  methods: {
  },
});
