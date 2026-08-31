import type { Metadata } from "next";
import {
  localRegistrationConfigured,
  oidcConfigured,
} from "../lib/server/accountSession";

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
  LOCAL_ACCOUNT_ALREADY_EXISTS: "该用户名已存在，请直接登录。",
  LOCAL_REGISTRATION_UNAVAILABLE: "注册暂时不可用，请稍后重试。",
};

export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; returnTo?: string }>;
}) {
  const parameters = await searchParams;
  const registrationConfigured = localRegistrationConfigured();
  const returnTo = parameters.returnTo?.startsWith("/") && !parameters.returnTo.startsWith("//")
    ? parameters.returnTo
    : "/";
  const error = parameters.error
    ? errorMessages[parameters.error] ?? "注册未完成。"
    : null;
  return (
    <section className="auth-page" aria-labelledby="register-title">
      <div className="auth-card">
        <span className="eyebrow">LOCAL DEVELOPMENT IDENTITY</span>
        <h1 id="register-title">注册 ELMOS 账户</h1>
        <p>注册功能只为本地开发环境提供。账户密码使用 scrypt 哈希保存，生产环境仍由企业 OIDC 负责身份注册与登录。</p>
        {error && <div className="auth-error" role="alert">{error}</div>}
        {registrationConfigured ? (
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
              <span>邮箱（可选）</span>
              <input name="email" type="email" autoComplete="email" maxLength={254} />
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
        ) : (
          <div className="auth-not-configured" role="status">
            <strong>本地注册不可用</strong>
            <span>{oidcConfigured() ? "当前部署使用企业 OIDC；请在身份提供商处完成注册。" : "请在非生产环境配置本地账户存储，或先配置企业 OIDC。"}</span>
          </div>
        )}
        <div className="auth-links">
          <span>已有账户？</span>
          <a className="text-link" href={`/login?${new URLSearchParams({ returnTo })}`}>返回登录</a>
        </div>
        <small>本地账户只授予 DEVELOPER 最小权限；生产部署不会接受本地账户凭据。</small>
      </div>
    </section>
  );
}
