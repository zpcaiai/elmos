/** Native WeChat candidate emitter for explicit HAND_PORTED components. */
import type { ManualComponentIR } from "./manual-component-ir";

export type WechatHandPortRole = "workbench" | "provider" | "shell" | "table" | "disclosure" | "icon" | "chart";

export interface WechatHandPortEmission {
  role: WechatHandPortRole;
  files: Record<"js" | "json" | "wxml" | "wxss", string>;
}

function roleFor(ir: ManualComponentIR): WechatHandPortRole {
  const name = ir.source.componentName;
  const domains = new Set(ir.platformSemantics.map((item) => item.domain));
  if (domains.has("TABLE")) return "table";
  if (domains.has("DISCLOSURE")) return "disclosure";
  if (domains.has("SVG") || name === "Icon") return "icon";
  if (/Graph|Chart|Matrix|Dashboard|Meter/.test(name)) return "chart";
  if (/Provider$/.test(name)) return "provider";
  if (/Shell|Layout|Page$/.test(name) || domains.has("SLOT") || domains.has("DOCUMENT_ROOT")) return "shell";
  return "workbench";
}

function xml(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function template(role: WechatHandPortRole, labels: string[]): string {
  const labelNodes = labels.slice(0, 6).map((label) => `    <text class="source-label">${xml(label)}</text>`).join("\n");
  const status = `<view class="status status--{{status}}"><text>{{status}}</text><text wx:if="{{error}}"> · {{error}}</text></view>`;
  if (role === "provider") return `<view class="provider" data-component="{{componentName}}">\n  <slot />\n  ${status}\n</view>\n`;
  if (role === "icon") return `<view class="icon" role="img" aria-label="{{accessibleName}}"><text>{{iconText}}</text></view>\n`;
  if (role === "table") return `<view class="card" data-component="{{componentName}}">\n  <view class="heading"><text>{{title}}</text><button size="mini" bindtap="reload">刷新</button></view>\n  ${status}\n  <scroll-view scroll-x class="table-scroll">\n    <view wx:for="{{rows}}" wx:key="key" class="table-row"><text class="table-key">{{item.key}}</text><text>{{item.value}}</text></view>\n  </scroll-view>\n</view>\n`;
  if (role === "disclosure") return `<view class="card" data-component="{{componentName}}">\n  <button class="heading" bindtap="toggleExpanded" aria-expanded="{{expanded}}">{{title}}</button>\n  <view wx:if="{{expanded}}" class="content">\n${labelNodes}\n    <view wx:for="{{rows}}" wx:key="key"><text>{{item.key}}: {{item.value}}</text></view>\n  </view>\n</view>\n`;
  if (role === "chart") return `<view class="card" data-component="{{componentName}}">\n  <view class="heading"><text>{{title}}</text><button size="mini" bindtap="reload">刷新</button></view>\n  ${status}\n  <view class="chart" wx:if="{{rows.length}}">\n    <view wx:for="{{rows}}" wx:key="key" class="bar-row"><text class="bar-label">{{item.key}}</text><view class="bar" style="width: {{item.width}}%"></view><text>{{item.value}}</text></view>\n  </view>\n  <view wx:else class="source-labels">\n${labelNodes}\n  </view>\n</view>\n`;
  if (role === "shell") return `<view class="shell" data-component="{{componentName}}">\n  <view class="heading"><text>{{title}}</text></view>\n  ${status}\n  <slot />\n  <view class="source-labels">\n${labelNodes}\n  </view>\n</view>\n`;
  return `<view class="card" data-component="{{componentName}}">\n  <view class="heading"><text>{{title}}</text><button size="mini" bindtap="reload">刷新</button></view>\n  ${status}\n  <view class="source-labels">\n${labelNodes}\n  </view>\n  <view class="actions">\n    <button wx:for="{{actions}}" wx:key="id" size="mini" data-action="{{item.id}}" bindtap="runAction">{{item.label}}</button>\n  </view>\n  <view wx:for="{{rows}}" wx:key="key" class="data-row"><text>{{item.key}}</text><text>{{item.value}}</text></view>\n</view>\n`;
}

function style(tokens: string[]): string {
  const tokenRules = tokens.map((token) => `.source-${token.replace(/[^A-Za-z0-9_-]/g, "-")} { box-sizing: border-box; }`).join("\n");
  return `.card, .shell, .provider { box-sizing: border-box; margin: 20rpx 0; padding: 24rpx; border: 1rpx solid #d7deea; border-radius: 16rpx; background: #fff; color: #172033; }
.heading { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; font-size: 30rpx; font-weight: 600; }
.status { margin: 12rpx 0; color: #58677d; font-size: 24rpx; }
.status--failed, .status--configuration-required { color: #a51d2d; }
.source-labels, .content { display: flex; flex-direction: column; gap: 8rpx; margin-top: 12rpx; }
.source-label { color: #46566f; font-size: 24rpx; }
.actions { display: flex; flex-wrap: wrap; gap: 12rpx; margin: 16rpx 0; }
.data-row, .table-row, .bar-row { display: flex; align-items: center; gap: 16rpx; min-height: 56rpx; border-top: 1rpx solid #edf0f5; }
.data-row > text:first-child, .table-key, .bar-label { width: 220rpx; color: #59677a; }
.table-scroll { width: 100%; }
.table-row { min-width: 900rpx; }
.chart { display: flex; flex-direction: column; gap: 12rpx; }
.bar { min-width: 4rpx; max-width: 280rpx; height: 20rpx; border-radius: 10rpx; background: #3568d4; }
.icon { display: inline-flex; align-items: center; justify-content: center; width: 48rpx; height: 48rpx; font-size: 36rpx; }
${tokenRules}${tokenRules ? "\n" : ""}`;
}

export function emitWechatHandPort(ir: ManualComponentIR): WechatHandPortEmission {
  const role = roleFor(ir);
  const contract = {
    schemaVersion: "1.0",
    componentName: ir.source.componentName,
    title: ir.textLabels[0] ?? ir.source.componentName,
    role,
    source: ir.source,
    blocker: ir.blocker,
    props: ir.props,
    states: ir.state.map((item) => ({ name: item.name, type: item.type })),
    hooks: [...new Set(ir.hooks.map((item) => item.callee))],
    resources: [...new Set(ir.effects.flatMap((effect) => effect.resources))],
    apiPaths: ir.apiPaths,
    labels: ir.textLabels,
    adapters: ir.targetPlan.adapters,
    obligations: ir.obligations.map((item) => item.id),
    irDigest: ir.irDigest,
  };
  return {
    role,
    files: {
      js: `const { createHandPortComponent } = require("../../runtime/hand-port-runtime");\n\nComponent(createHandPortComponent(${JSON.stringify(contract, null, 2)}));\n`,
      json: `${JSON.stringify({ component: true, styleIsolation: "apply-shared" }, null, 2)}\n`,
      wxml: template(role, ir.textLabels),
      wxss: style(ir.cssModuleTokens),
    },
  };
}

export const WECHAT_HAND_PORT_RUNTIME = `const platform = require("./platform-adapters");

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
        const base = String(this.properties.apiBaseUrl || "").replace(/\/$/, "");
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
`;

export const WECHAT_PLATFORM_ADAPTERS = `const ICONS = Object.freeze({
  info: "ⓘ", success: "✓", warning: "!", error: "×", play: "▶", settings: "⚙",
});

function iconText(name) { return ICONS[name] || ICONS.info; }

function providerState(componentName) {
  if (componentName === "AccountSessionProvider") {
    return { status: wx.getStorageSync("elmos.account.status") || "anonymous" };
  }
  if (componentName === "UiPreferencesProvider") {
    return {
      locale: wx.getStorageSync("elmos.ui.locale") || "zh-CN",
      theme: wx.getStorageSync("elmos.ui.theme") || "system",
    };
  }
  return {};
}

function navigate(path) {
  if (typeof path !== "string" || !path.startsWith("/pages/")) return Promise.reject(new Error("NAVIGATION_PATH_NOT_ALLOWLISTED"));
  return new Promise((resolve, reject) => wx.navigateTo({ url: path, success: resolve, fail: reject }));
}

module.exports = { iconText, providerState, navigate };
`;
