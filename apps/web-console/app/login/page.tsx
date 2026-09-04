import type { Metadata } from "next";
import {
  localCredentialsConfigured,
  localRegistrationConfigured,
  oidcConfigured,
} from "../lib/server/accountSession";

export const metadata: Metadata = { title: "用户登录" };
export const dynamic = "force-dynamic";

const errorMessages: Record<string, string> = {
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
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; registered?: string; returnTo?: string }>;
}) {
  const parameters = await searchParams;
  const configured = oidcConfigured();
  const localConfigured = localCredentialsConfigured();
  const registrationConfigured = localRegistrationConfigured();
  const returnTo = parameters.returnTo?.startsWith("/") && !parameters.returnTo.startsWith("//")
    ? parameters.returnTo
    : "/";
  const error = parameters.error ? errorMessages[parameters.error] ?? "登录未完成，未建立账户会话。" : null;
  return (
    <section className="auth-page user-auth-page" aria-labelledby="login-title">
      <div className="auth-card user-auth-card">
        <span className="eyebrow">USER ACCESS · EMAIL</span>
        <h1 id="login-title">用户登录</h1>
        <p>使用已注册邮箱进入 ELMOS 用户控制中心。租户、角色和权限只由服务端已验证的账户会话决定。</p>

        <div className="user-scope-notice" role="note">
          <strong>登录后可以使用的功能</strong>
          <span>Spring 老项目翻新、全库跨语言转换、多语言项目生成、国产数据库 SQL 转换、多模态输入、前端转换工厂、代码仓库工作区、任务编排与模型路由、迁移工坊、功能能力中心、套餐与用量、账户与组织。</span>
          <small>平台运营页面（运营管理端、观测存证、契约治理、商业化控制面、证据闭环、验证沙箱、冒烟运行）不对用户账户开放。</small>
        </div>
        {error && <div className="auth-error" role="alert">{error}</div>}
        {parameters.registered === "1" && (
          <div className="auth-success" role="status">账户已创建，请使用新账户登录。</div>
        )}
        {configured && (
          <a
            className="button button-primary"
            href={`/api/auth/login?${new URLSearchParams({ mode: "USER", returnTo })}`}
          >
            使用企业账户登录用户中心
          </a>
        )}
        {localConfigured && (
          <form className="auth-form" method="post" action="/api/auth/login">
            <h2>使用邮箱登录</h2>
            <p>本地邮箱密码登录仅限 localhost 开发测试；生产环境永久禁用。</p>
            <input type="hidden" name="returnTo" value={returnTo} />
            <input type="hidden" name="loginMode" value="USER" />
            <label>
              <span>邮箱</span>
              <input
                name="email"
                type="text"
                defaultValue="test@example.test"
                autoComplete="username"
                maxLength={254}
                required
              />
            </label>
            <label>
              <span>密码</span>
              <input name="password" type="password" autoComplete="current-password" required />
            </label>
            <button className="button button-primary" type="submit">使用邮箱登录</button>
          </form>
        )}
        {registrationConfigured && (
          <div className="auth-links">
            <span>还没有本地账户？</span>
            <a className="text-link" href={`/register?${new URLSearchParams({ returnTo })}`}>注册本地账户</a>
          </div>
        )}
        <div className="admin-entry-callout" aria-label="管理员专用入口">
          <div>
            <strong>管理员专用入口</strong>
            <span>管理员登录与普通用户登录使用独立页面和受控会话，可见页面也完全不同。</span>
          </div>
          <a className="button admin-entry-button" href="/admin/login">进入管理员登录</a>
        </div>
        {!configured && !localConfigured && (
          <div className="auth-not-configured" role="status">
            <strong>身份提供商未配置</strong>
            <span>需要设置精确的 issuer、授权端点、令牌端点、JWKS、client 和回调地址。</span>
          </div>
        )}
        <small>普通用户登录不会授予管理员权限。未登录、令牌过期、权限不足或租户不匹配时，服务端 API 均会拒绝操作。</small>
      </div>
    </section>
  );
}
