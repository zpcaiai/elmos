const ICONS = Object.freeze({
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
