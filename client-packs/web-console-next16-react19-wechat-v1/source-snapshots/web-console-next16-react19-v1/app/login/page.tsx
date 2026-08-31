import type { Metadata } from "next";
import {
  localCredentialsConfigured,
  oidcConfigured,
} from "../lib/server/accountSession";

export const metadata: Metadata = { title: "登录" };
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
  LOCAL_CREDENTIALS_UNAVAILABLE: "本地测试账号当前不可用。",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; returnTo?: string }>;
}) {
  const parameters = await searchParams;
  const configured = oidcConfigured();
  const localConfigured = localCredentialsConfigured();
  const returnTo = parameters.returnTo?.startsWith("/") ? parameters.returnTo : "/";
  const error = parameters.error ? errorMessages[parameters.error] ?? "登录未完成，未建立账户会话。" : null;
  return (
    <section className="auth-page" aria-labelledby="login-title">
      <div className="auth-card">
        <span className="eyebrow">Enterprise identity</span>
        <h1 id="login-title">登录 ELMOS 控制中心</h1>
        <p>通过企业 OIDC 身份提供商登录。租户、角色和权限只从已验证的令牌声明派生。</p>
        {error && <div className="auth-error" role="alert">{error}</div>}
        {configured && (
          <a
            className="button button-primary"
            href={`/api/auth/login?${new URLSearchParams({ returnTo })}`}
          >
            使用企业账户登录
          </a>
        )}
        {localConfigured && (
          <form className="auth-form" method="post" action="/api/auth/login">
            <h2>本地测试账号</h2>
            <p>仅限 localhost 的开发测试登录，默认账号为 test/test；生产环境永久禁用。</p>
            <input type="hidden" name="returnTo" value={returnTo} />
            <label>
              <span>用户名</span>
              <input name="username" defaultValue="test" autoComplete="username" required />
            </label>
            <label>
              <span>密码</span>
              <input name="password" type="password" autoComplete="current-password" required />
            </label>
            <button className="button button-primary" type="submit">使用本地测试账号登录</button>
          </form>
        )}
        {!configured && !localConfigured && (
          <div className="auth-not-configured" role="status">
            <strong>身份提供商未配置</strong>
            <span>需要设置精确的 issuer、授权端点、令牌端点、JWKS、client 和回调地址。</span>
          </div>
        )}
        <small>未登录、令牌过期、权限不足或租户不匹配时，服务端 API 均会拒绝操作。</small>
      </div>
    </section>
  );
}
