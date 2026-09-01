import type { Metadata } from "next";
import {
  ADMINISTRATOR_EMAIL,
  oidcConfigured,
} from "../../lib/server/accountSession";
import { safeOperationsReturnTo } from "../../lib/surfaceAudience";

export const metadata: Metadata = { title: "管理员登录" };
export const dynamic = "force-dynamic";

const errorMessages: Record<string, string> = {
  OIDC_AUTHORIZATION_REJECTED: "身份提供商拒绝了本次管理员登录。",
  OIDC_CALLBACK_INVALID: "管理员登录回调缺少必要参数，请重新开始。",
  OIDC_CALLBACK_FAILED: "管理员身份校验失败，请重新尝试。",
  OIDC_STATE_INVALID: "管理员登录 state 已过期或不匹配，请重新开始。",
  OIDC_NONCE_INVALID: "管理员登录 nonce 校验失败，未建立会话。",
  OIDC_TOKEN_EXCHANGE_REJECTED: "身份提供商拒绝管理员令牌交换。",
  EMAIL_CREDENTIALS_INVALID: "管理员邮箱或密码错误。",
  LOCAL_CREDENTIALS_INVALID: "管理员邮箱或密码错误。",
  LOCAL_CREDENTIALS_DISABLED: "本地管理员凭据未启用。",
  LOCAL_CREDENTIALS_LOOPBACK_ONLY: "本地管理员登录仅允许从 localhost 使用。",
  LOCAL_CREDENTIALS_CONFIGURATION_INVALID: "本地管理员凭据配置无效。",
  LOCAL_CREDENTIALS_LOCKED: "管理员账户暂时锁定，请稍后重试。",
  LOCAL_CREDENTIALS_UNAVAILABLE: "本地管理员登录当前不可用。",
  LOGIN_MODE_INVALID: "管理员登录入口无效，请从当前页面重新开始。",
  ADMIN_EMAIL_REQUIRED: "该邮箱不是获准的管理员账户。",
  ADMIN_EMAIL_NOT_VERIFIED: "管理员邮箱尚未通过可信身份提供商验证。",
  ADMIN_LOGIN_ENTRY_REQUIRED: "管理员账户必须从当前专用入口登录。",
  ADMIN_LOGIN_NOTIFICATION_NOT_CONFIGURED: "管理员登录安全通知尚未配置，本次未建立管理员会话。",
  ADMIN_LOGIN_NOTIFICATION_CONFIGURATION_INVALID: "管理员登录安全通知配置无效，本次未建立管理员会话。",
  ADMIN_LOGIN_NOTIFICATION_SECRET_FILE_UNSAFE: "管理员登录安全通知密钥文件权限不安全，本次未建立管理员会话。",
  ADMIN_LOGIN_NOTIFICATION_SECRET_FILE_UNAVAILABLE: "管理员登录安全通知密钥文件不可用，本次未建立管理员会话。",
  ADMIN_LOGIN_NOTIFICATION_UNAVAILABLE: "管理员登录安全通知暂不可用，本次未建立管理员会话。",
  ADMIN_LOGIN_NOTIFICATION_RATE_LIMITED: "管理员登录安全通知受到限流，本次未建立管理员会话。",
  ADMIN_LOGIN_NOTIFICATION_REJECTED: "管理员登录安全通知被邮件服务拒绝，本次未建立管理员会话。",
  ADMIN_LOGIN_NOTIFICATION_RESPONSE_INVALID: "管理员登录安全通知未返回有效投递凭据，本次未建立管理员会话。",
  ADMIN_SESSION_REQUIRED: "请通过管理员专用入口重新登录。",
};

export default async function AdminLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; returnTo?: string }>;
}) {
  const parameters = await searchParams;
  const configured = oidcConfigured();
  const error = parameters.error
    ? errorMessages[parameters.error] ?? "管理员登录未完成，未建立管理员会话。"
    : null;
  const adminReturnTo = safeOperationsReturnTo(parameters.returnTo);

  return (
    <section className="auth-page admin-auth-page" aria-labelledby="admin-login-title">
      <div className="auth-card admin-auth-card">
        <span className="admin-auth-badge">管理员专用 · ADMIN ONLY</span>
        <span className="eyebrow">PRIVILEGED ACCESS</span>
        <h1 id="admin-login-title">管理员登录</h1>
        <p>此入口与普通用户登录独立。管理员权限只由服务端验证后的精确邮箱、登录模式和账户会话授予。</p>

        <div className="admin-scope-notice" role="note">
          <strong>管理员端可见页面</strong>
          <span>运营管理端、全链路观测与存证、契约治理与变异、商业化控制面、现代化证据闭环、转换验证沙箱、一键冒烟运行。</span>
          <small>普通用户账户即使拿到链接也无法打开这些页面；服务端会重定向回本入口。</small>
        </div>

        <div className="admin-identity-notice" role="note">
          <span>唯一管理员邮箱</span>
          <strong>{ADMINISTRATOR_EMAIL}</strong>
          <small>其他邮箱即使访问此页面，也不会获得任何管理员权限。</small>
        </div>

        {error && <div className="auth-error" role="alert">{error}</div>}

        {configured && (
          <a
            className="button admin-login-primary"
            href={`/api/auth/login?${new URLSearchParams({
              mode: "ADMIN",
              returnTo: adminReturnTo,
            })}`}
          >
            使用企业账户登录管理中心
          </a>
        )}

        {!configured && (
          <div className="auth-not-configured" role="status">
            <strong>管理员身份提供商未配置</strong>
            <span>管理员登录失败关闭：必须先配置受信任的企业 OIDC，不提供本地密码或短期令牌降级入口。</span>
          </div>
        )}

        <div className="admin-login-notification" role="note">
          <strong>登录安全通知</strong>
          <span>每次管理员成功登录后，系统都会向 {ADMINISTRATOR_EMAIL} 发送安全通知。</span>
        </div>

        <div className="auth-links admin-auth-links">
          <span>不是管理员？</span>
          <a className="text-link" href="/login">返回用户登录，使用产品功能</a>
        </div>
        <small>管理员页面不会通过客户端字段、链接或隐藏表单提升权限；最终授权始终由服务端决定。</small>
      </div>
    </section>
  );
}
