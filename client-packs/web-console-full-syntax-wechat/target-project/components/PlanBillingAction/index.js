// Top-level helpers and constants
try { var idempotencyKey = function idempotencyKey(prefix, current) {
    if (current.current === null)
        current.current = `${prefix}-${crypto.randomUUID()}`;
    return current.current;
} } catch(e) {}
try { var json = async function json(response) {
    try {
        return await response.json();
    }
    catch {
        return {};
    }
} } catch(e) {}
try { var errorMessage = function errorMessage(payload, fallback) {
    if (payload.code === "TRIAL_ALREADY_USED")
        return "该组织或已验证身份已使用过免费体验。";
    if (payload.code === "ACCOUNT_SESSION_REQUIRED")
        return "请先登录后再管理套餐。";
    return payload.message || fallback;
} } catch(e) {}
try { var isTrustedCheckoutHost = function isTrustedCheckoutHost(provider, hostname) {
    if (provider === "STRIPE_CHECKOUT") {
        return hostname === "stripe.com" || hostname.endsWith(".stripe.com");
    }
    if (provider === "ALIPAY_CHECKOUT") {
        // openapi.alipay.com 是生产网关，openapi.alipaydev.com 是沙箱。
        // 沙箱域名保留是为了让联调走同一条代码路径——联调绕过校验，
        // 等于上线前从没验过这段校验。
        return hostname === "openapi.alipay.com" || hostname === "openapi.alipaydev.com";
    }
    // 微信 Native 不走跳转，走到这里说明上游给错了形态
    return false;
} } catch(e) {}
try { var planName = function planName(planId) {
    if (planId === "elmos-free-trial")
        return "免费体验";
    if (planId === "elmos-pro-monthly")
        return "专业月付";
    if (planId === "elmos-pro-annual")
        return "专业年付";
    return planId;
} } catch(e) {}
try { var formatDate = function formatDate(value) {
    const parsed = new Date(value);
    return Number.isFinite(parsed.getTime())
        ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "long" }).format(parsed)
        : "未知日期";
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    plan: {
      type: null,
      value: null,
    },
    orderable: {
      type: null,
      value: null,
    },
  },
  data: {
    key: {"current":null},
    pending: false,
    message: "",
    failed: false,
    qrCode: null,
  },
  lifetimes: {
    attached() {
      const setPending = (val) => { this.setData({ pending: typeof val === "function" ? val(this.data.pending) : val }); };
      const setMessage = (val) => { this.setData({ message: typeof val === "function" ? val(this.data.message) : val }); };
      const setFailed = (val) => { this.setData({ failed: typeof val === "function" ? val(this.data.failed) : val }); };
      const setQrCode = (val) => { this.setData({ qrCode: typeof val === "function" ? val(this.data.qrCode) : val }); };
      const key = { current: { focus: () => {}, scrollIntoView: () => {} } };
    },
    detached() {
    },
  },
  methods: {
  },
});
