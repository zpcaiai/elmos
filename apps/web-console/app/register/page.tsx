import type { Metadata } from "next";
import {
  localRegistrationConfigured,
  oidcConfigured,
} from "../lib/server/accountSession";
import {
  descopeConfigured,
  descopeWechatConfigured,
} from "../lib/server/descopeIdentity";

export const metadata: Metadata = { title: "注册" };
export const dynamic = "force-dynamic";

const errorMessages: Record<string, string> = {
  LOCAL_REGISTRATION_DISABLED: "本地注册未启用。",
  LOCAL_REGISTRATION_STORE_NOT_CONFIGURED: "本地注册存储未配置，请联系开发环境维护者。",
  LOCAL_REGISTRATION_STORE_INVALID: "本地账户存储不可用，请检查开发环境配置。",
  LOCAL_REGISTRATION_USERNAME_INVALID: "用户名需为 3 至 200 个字符，仅支持字母、数字及 . _ : - @ /。",
  LOCAL_REGISTRATION_PASSWORD_WEAK: "密码至少需要 8 个字符。",
  LOCAL_REGISTRATION_PASSWORD_MISMATCH: "两次输入的密码不一致。",
  LOCAL_REGISTRATION_DISPLAY_NAME_INVALID: "显示名称需为 2 至 160 个字符。",
  LOCAL_REGISTRATION_EMAIL_INVALID: "邮箱地址无效。",
  LOCAL_REGISTRATION_ADMIN_EMAIL_RESERVED: "管理员邮箱不能通过普通用户注册创建。",
  LOCAL_ACCOUNT_ALREADY_EXISTS: "该用户名或邮箱已存在，请直接登录。",
  LOCAL_REGISTRATION_UNAVAILABLE: "注册暂时不可用，请稍后重试。",
  DESCOPE_EMAIL_INVALID: "请输入有效邮箱地址。",
  DESCOPE_PHONE_INVALID: "手机号需包含国家区号，例如 +8613812345678。",
  DESCOPE_OTP_START_REJECTED: "验证码发送失败；账户可能已存在、方式未启用或请求过于频繁。",
  DESCOPE_OTP_CODE_INVALID: "验证码格式无效。",
  DESCOPE_OTP_VERIFY_REJECTED: "验证码错误、已过期或尝试次数过多。",
  DESCOPE_CHALLENGE_EXPIRED: "验证码会话已过期，请重新注册。",
  DESCOPE_ADMIN_EMAIL_RESERVED: "管理员邮箱不能通过普通用户注册入口创建。",
  DESCOPE_WECHAT_NOT_CONFIGURED: "微信开放平台注册尚未配置。",
  DESCOPE_WECHAT_START_REJECTED: "微信注册启动失败，请稍后重试。",
  DESCOPE_WECHAT_AUTHORIZATION_REJECTED: "微信授权被取消或拒绝。",
  DESCOPE_WECHAT_EXCHANGE_REJECTED: "微信身份校验失败，请重新扫码。",
  ACCOUNT_SESSION_SECRET_NOT_CONFIGURED: "账户会话密钥尚未配置，未创建会话。",
};

export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; returnTo?: string; verify?: string }>;
}) {
  const parameters = await searchParams;
  const registrationConfigured = localRegistrationConfigured();
  const descopeReady = descopeConfigured();
  const wechatReady = descopeWechatConfigured();
  const returnTo = parameters.returnTo?.startsWith("/") && !parameters.returnTo.startsWith("//")
    ? parameters.returnTo
    : "/";
  const error = parameters.error
    ? errorMessages[parameters.error] ?? "注册未完成。"
    : null;
  return (
    <section className="auth-page" aria-labelledby="register-title">
      <div className="auth-card">
        <span className="eyebrow">USER REGISTRATION · MULTI-CHANNEL</span>
        <h1 id="register-title">注册 ELMOS 账户</h1>
        <p>使用邮箱验证码、手机短信验证码或微信扫码创建普通用户账户。身份由 Descope 验证，ELMOS 服务端只授予普通用户最小权限。</p>
        {error && <div className="auth-error" role="alert">{error}</div>}
        {parameters.verify === "1" && descopeReady && (
          <form className="auth-form otp-verify-form" method="post" action="/api/auth/descope/otp/verify">
            <h2>输入一次性验证码</h2>
            <p>验证码已发送。验证通过后将创建账户并进入用户中心。</p>
            <label><span>验证码</span><input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{4,10}" minLength={4} maxLength={10} required autoFocus /></label>
            <button className="button button-primary" type="submit">验证并完成注册</button>
            <a className="text-link" href={`/register?${new URLSearchParams({ returnTo })}`}>重新选择注册方式</a>
          </form>
        )}
        {descopeReady && parameters.verify !== "1" && (
          <div className="auth-method-grid" aria-label="用户注册方式">
            <form className="auth-method-card" method="post" action="/api/auth/descope/otp/start">
              <span className="auth-method-icon" aria-hidden="true">@</span>
              <h2>邮箱注册</h2>
              <p>填写名称和邮箱，通过一次性验证码完成注册。</p>
              <input type="hidden" name="channel" value="EMAIL" />
              <input type="hidden" name="intent" value="REGISTER" />
              <input type="hidden" name="loginMode" value="USER" />
              <input type="hidden" name="returnTo" value={returnTo} />
              <label><span>显示名称</span><input name="displayName" autoComplete="name" minLength={2} maxLength={160} required /></label>
              <label><span>邮箱</span><input name="loginId" type="email" autoComplete="email" maxLength={254} required /></label>
              <button className="button button-primary" type="submit">发送邮箱验证码</button>
            </form>
            <form className="auth-method-card" method="post" action="/api/auth/descope/otp/start">
              <span className="auth-method-icon" aria-hidden="true">☎</span>
              <h2>手机号注册</h2>
              <p>填写名称和含国家区号的手机号，通过短信验证码注册。</p>
              <input type="hidden" name="channel" value="SMS" />
              <input type="hidden" name="intent" value="REGISTER" />
              <input type="hidden" name="loginMode" value="USER" />
              <input type="hidden" name="returnTo" value={returnTo} />
              <label><span>显示名称</span><input name="displayName" autoComplete="name" minLength={2} maxLength={160} required /></label>
              <label><span>手机号</span><input name="loginId" type="tel" inputMode="tel" autoComplete="tel" placeholder="+8613812345678" maxLength={18} required /></label>
              <button className="button button-secondary" type="submit">发送短信验证码</button>
            </form>
            <form className={`auth-method-card wechat-auth-card${wechatReady ? "" : " auth-method-disabled"}`} method="post" action="/api/auth/descope/wechat/start">
              <span className="auth-method-icon wechat-icon" aria-hidden="true">微</span>
              <h2>微信扫码注册</h2>
              <p>{wechatReady ? "打开微信二维码，扫码确认后创建普通用户账户。" : "代码已接入；配置微信开放平台 AppID 与密钥后启用真实二维码。"}</p>
              <input type="hidden" name="intent" value="REGISTER" />
              <input type="hidden" name="returnTo" value={returnTo} />
              <button className="button wechat-login-button" type="submit" disabled={!wechatReady}>{wechatReady ? "打开微信注册二维码" : "微信凭据待配置"}</button>
            </form>
          </div>
        )}
        {!descopeReady && registrationConfigured ? (
          <form className="auth-form" method="post" action="/api/auth/register">
            <h2>创建本地账户</h2>
            <p>创建后会自动建立本地短期会话，并进入控制中心。</p>
            <input type="hidden" name="returnTo" value={returnTo} />
            <label>
              <span>用户名</span>
              <input name="username" autoComplete="username" minLength={3} maxLength={200} required />
            </label>
            <label>
              <span>显示名称</span>
              <input name="displayName" autoComplete="name" minLength={2} maxLength={160} required />
            </label>
            <label>
              <span>邮箱</span>
              <input name="email" type="email" autoComplete="email" inputMode="email" maxLength={254} required />
            </label>
            <label>
              <span>密码</span>
              <input name="password" type="password" autoComplete="new-password" minLength={8} maxLength={1024} required />
            </label>
            <label>
              <span>确认密码</span>
              <input name="passwordConfirmation" type="password" autoComplete="new-password" minLength={8} maxLength={1024} required />
            </label>
            <button className="button button-primary" type="submit">创建账户</button>
          </form>
        ) : !descopeReady ? (
          <div className="auth-not-configured" role="status">
            <strong>注册身份提供商不可用</strong>
            <span>{oidcConfigured() ? "当前部署仅配置企业 OIDC；请在身份提供商处完成注册。" : "请先配置 Descope 用户认证集成。"}</span>
          </div>
        ) : null}
        <div className="auth-links">
          <span>已有账户？</span>
          <a className="text-link" href={`/login?${new URLSearchParams({ returnTo })}`}>返回登录</a>
        </div>
        <small>所有自助注册账户均为普通用户，只授予 DEVELOPER 最小权限；{`zpchoney@gmail.com`} 不能通过此入口获得管理员权限。</small>
      </div>
    </section>
  );
}
