// Top-level helpers and constants
try { const dynamic = "force-dynamic"; } catch(e) {}
try { const errorMessages = {
    OIDC_AUTHORIZATION_REJECTED: "身份提供商拒绝了本次登录。",
    OIDC_CALLBACK_INVALID: "登录回调缺少必要参数，请重新开始。",
    OIDC_CALLBACK_FAILED: "登录校验失败，请重新尝试或联系管理员。",
    OIDC_STATE_INVALID: "登录 state 已过期或不匹配，请重新开始。",
    OIDC_NONCE_INVALID: "登录 nonce 校验失败，未建立会话。",
    OIDC_TOKEN_EXCHANGE_REJECTED: "身份提供商拒绝令牌交换。",
    OIDC_TENANT_CLAIM_INVALID: "账户没有有效的 organization_id 租户声明。",
    OIDC_SUBJECT_CLAIM_INVALID: "账户没有有效的主体标识。",
    LOCAL_CREDENTIALS_INVALID: "本地测试账号或密码错误。",
    LOCAL_CREDENTIALS_DISABLED: "本地测试账号未启用。",
    LOCAL_CREDENTIALS_LOOPBACK_ONLY: "本地测试账号仅允许从 localhost 使用。",
    LOCAL_CREDENTIALS_CONFIGURATION_INVALID: "本地测试账号配置无效。",
    LOCAL_CREDENTIALS_LOCKED: "本地账户暂时锁定，请稍后重试。",
    LOCAL_CREDENTIALS_UNAVAILABLE: "本地测试账号当前不可用。",
    EMAIL_CREDENTIALS_INVALID: "邮箱或密码错误。",
    LOGIN_MODE_INVALID: "登录入口无效，请从当前页面重新开始。",
    ADMIN_LOGIN_ENTRY_REQUIRED: "管理员账户必须从独立的管理员入口登录。",
    DESCOPE_EMAIL_INVALID: "请输入有效邮箱地址。",
    DESCOPE_PHONE_INVALID: "手机号需包含国家区号，例如 +8613812345678。",
    DESCOPE_OTP_START_REJECTED: "验证码发送失败；账户不存在、方式未启用或请求过于频繁。",
    DESCOPE_OTP_CODE_INVALID: "验证码格式无效。",
    DESCOPE_OTP_VERIFY_REJECTED: "验证码错误、已过期或尝试次数过多。",
    DESCOPE_CHALLENGE_EXPIRED: "验证码会话已过期，请重新开始。",
    DESCOPE_TOKEN_INVALID: "身份提供商会话校验失败，未建立账户会话。",
    DESCOPE_WECHAT_NOT_CONFIGURED: "微信开放平台登录尚未配置。",
    DESCOPE_WECHAT_START_REJECTED: "微信登录启动失败，请稍后重试。",
    DESCOPE_WECHAT_AUTHORIZATION_REJECTED: "微信授权被取消或拒绝。",
    DESCOPE_WECHAT_EXCHANGE_REJECTED: "微信登录校验失败，请重新扫码。",
    ACCOUNT_SESSION_SECRET_NOT_CONFIGURED: "账户会话密钥尚未配置，未建立会话。",
}; } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    searchParams: {
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
