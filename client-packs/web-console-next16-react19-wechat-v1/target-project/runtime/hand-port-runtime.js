const platform = require("./platform-adapters");

function plain(value, depth) {
  if (depth > 6) return "[depth-limit]";
  if (value === null || value === undefined) return value === undefined ? null : value;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.slice(0, 200).map((item) => plain(item, depth + 1));
  if (value instanceof Map) return Array.from(value.entries()).map(([key, item]) => ({ key: String(key), value: plain(item, depth + 1) }));
  if (value instanceof Set) return Array.from(value.values()).map((item) => plain(item, depth + 1));
  if (Object.prototype.toString.call(value) === "[object Object]") {
    const result = {};
    Object.keys(value).sort().slice(0, 200).forEach((key) => { result[key] = plain(value[key], depth + 1); });
    return result;
  }
  return String(value);
}

function rowsFor(value) {
  const normalized = plain(value, 0);
  const pairs = Array.isArray(normalized)
    ? normalized.map((item, index) => ({ key: String(index + 1), value: item }))
    : normalized && typeof normalized === "object"
      ? Object.keys(normalized).map((key) => ({ key, value: normalized[key] }))
      : [{ key: "value", value: normalized }];
  const numeric = pairs.map((item) => typeof item.value === "number" ? Math.abs(item.value) : 0);
  const max = Math.max(1, ...numeric);
  return pairs.slice(0, 200).map((item, index) => ({
    key: item.key,
    value: typeof item.value === "object" ? JSON.stringify(item.value) : String(item.value ?? ""),
    width: Math.max(2, Math.round((numeric[index] / max) * 100)),
  }));
}

function createHandPortComponent(contract) {
  return {
    options: { multipleSlots: true },
    properties: {
      apiBaseUrl: { type: String, value: "" },
      initialPayload: { type: Object, value: null },
      accessibleName: { type: String, value: contract.title },
      icon: { type: String, value: "info" },
    },
    data: {
      componentName: contract.componentName,
      title: contract.title,
      status: "ready",
      error: "",
      expanded: false,
      rows: [],
      actions: contract.apiPaths.map((path, index) => ({ id: String(index), label: path })),
      iconText: platform.iconText("info"),
    },
    observers: {
      initialPayload(value) {
        if (value !== null && value !== undefined) this.setData({ rows: rowsFor(value), status: "ready", error: "" });
      },
      icon(value) { this.setData({ iconText: platform.iconText(value) }); },
    },
    lifetimes: {
      attached() {
        this.__requestEpoch = 0;
        this.__requestTasks = [];
        if (contract.role === "provider") {
          const provided = platform.providerState(contract.componentName);
          this.setData({ rows: rowsFor(provided), status: "ready" });
        }
      },
      detached() {
        this.__requestEpoch += 1;
        (this.__requestTasks || []).forEach((task) => { if (task && typeof task.abort === "function") task.abort(); });
        this.__requestTasks = [];
      },
    },
    methods: {
      toggleExpanded() { this.setData({ expanded: !this.data.expanded }); },
      runAction(event) {
        const index = Number(event.currentTarget.dataset.action || 0);
        this.reload(index);
      },
      reload(actionIndex) {
        const endpoint = contract.apiPaths[Number.isFinite(actionIndex) ? actionIndex : 0];
        if (!endpoint) {
          this.setData({ status: "ready", error: "No external request is required for this component." });
          return;
        }
        const base = String(this.properties.apiBaseUrl || "").replace(//$/, "");
        if (!base) {
          this.setData({ status: "configuration-required", error: "apiBaseUrl is required before network effects may run." });
          return;
        }
        const epoch = ++this.__requestEpoch;
        this.setData({ status: "loading", error: "" });
        const task = wx.request({
          url: base + endpoint,
          method: "GET",
          success: (response) => {
            if (epoch !== this.__requestEpoch) return;
            if (response.statusCode < 200 || response.statusCode >= 300) {
              this.setData({ status: "failed", error: "HTTP " + response.statusCode });
              return;
            }
            this.setData({ status: "ready", error: "", rows: rowsFor(response.data) });
          },
          fail: (error) => {
            if (epoch !== this.__requestEpoch) return;
            this.setData({ status: "failed", error: String(error && error.errMsg ? error.errMsg : "request failed") });
          },
          complete: () => { this.__requestTasks = (this.__requestTasks || []).filter((item) => item !== task); },
        });
        this.__requestTasks.push(task);
      },
    },
  };
}

module.exports = { createHandPortComponent, plain, rowsFor };
