"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useAccountSession } from "../components/AccountSessionProvider";
import styles from "./AccountOrganizationStudio.module.css";

type Organization = {
  organizationId: string;
  displayName: string;
  role: string;
  actorId: string;
};

type Member = {
  accountId: string;
  actorId: string;
  displayName: string;
  role: string;
  state: string;
  joinedAt: string;
};

type ErrorPayload = { code?: string; errorCode?: string; message?: string };

export function AccountOrganizationStudio({ embedded = false }: { embedded?: boolean } = {}) {
  const account = useAccountSession();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [members, setMembers] = useState<Member[]>([]);
  const [name, setName] = useState("");
  const [region, setRegion] = useState("cn-north");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("MEMBER");
  const [invitationToken, setInvitationToken] = useState("");
  const [acceptToken, setAcceptToken] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);

  const call = useCallback(async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const response = await fetch(`/api/account/${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
    const payload = await response.json() as T & ErrorPayload;
    if (!response.ok) {
      throw new Error(payload.code ?? payload.errorCode ?? payload.message ?? "ACCOUNT_REQUEST_REJECTED");
    }
    return payload;
  }, []);

  const loadOrganizations = useCallback(async () => {
    const result = await call<{ organizations: Organization[] }>("organizations");
    setOrganizations(result.organizations);
    setSelectedId((current) =>
      result.organizations.some((item) => item.organizationId === current)
        ? current
        : result.organizations[0]?.organizationId ?? "");
  }, [call]);

  const loadMembers = useCallback(async (organizationId: string) => {
    if (!organizationId) {
      setMembers([]);
      return;
    }
    const result = await call<{ members: Member[] }>(
      `organizations/${encodeURIComponent(organizationId)}/members`,
    );
    setMembers(result.members);
  }, [call]);

  useEffect(() => {
    if (account.status !== "authenticated") return;
    void loadOrganizations().catch((error: unknown) =>
      setFeedback(error instanceof Error ? error.message : "ACCOUNT_LOAD_FAILED"));
  }, [account.status, loadOrganizations]);

  useEffect(() => {
    void loadMembers(selectedId).catch((error: unknown) =>
      setFeedback(error instanceof Error ? error.message : "MEMBER_LOAD_FAILED"));
  }, [loadMembers, selectedId]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setFeedback("");
    try {
      await action();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "ACCOUNT_REQUEST_REJECTED");
    } finally {
      setBusy(false);
    }
  }

  function createOrganization(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const created = await call<Organization>("organizations", {
        method: "POST",
        body: JSON.stringify({ displayName: name, dataRegion: region }),
      });
      setName("");
      await loadOrganizations();
      setSelectedId(created.organizationId);
      setFeedback("组织已创建；成员关系已立即写入租户目录。");
    });
  }

  function invite(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const result = await call<{ invitationToken: string }>(
        `organizations/${encodeURIComponent(selectedId)}/invitations`,
        {
          method: "POST",
          body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
        },
      );
      setInvitationToken(result.invitationToken);
      setInviteEmail("");
      setFeedback("邀请已创建。请通过已批准的安全渠道发送一次性令牌。");
    });
  }

  function acceptInvitation(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const result = await call<{ organizationId: string }>("invitations/accept", {
        method: "POST",
        body: JSON.stringify({ token: acceptToken }),
      });
      setAcceptToken("");
      await loadOrganizations();
      setSelectedId(result.organizationId);
      setFeedback("邀请已接受，组织访问已生效。");
    });
  }

  function switchOrganization() {
    void run(async () => {
      await account.switchTenant(selectedId);
      setFeedback("当前组织已切换；后续控制面请求会再次验证成员关系。");
    });
  }

  function updateMember(member: Member, role: string) {
    void run(async () => {
      await call(
        `organizations/${encodeURIComponent(selectedId)}/members/${encodeURIComponent(member.accountId)}`,
        { method: "PATCH", body: JSON.stringify({ role }) },
      );
      await loadMembers(selectedId);
      setFeedback("成员角色已更新。");
    });
  }

  function removeMember(member: Member) {
    void run(async () => {
      await call(
        `organizations/${encodeURIComponent(selectedId)}/members/${encodeURIComponent(member.accountId)}`,
        { method: "DELETE" },
      );
      await loadMembers(selectedId);
      setFeedback("成员已移除；最后一位 Owner 受数据库保护，不能被移除。");
    });
  }

  if (account.status !== "authenticated") {
    if (embedded) return null;
    return (
      <section className={styles.page}>
        <header className="page-header">
          <div><span className="eyebrow">IDENTITY</span><h1>账户与组织</h1>
            <p>请先使用企业 OIDC 账户登录，再创建或加入组织。</p></div>
        </header>
      </section>
    );
  }

  const selected = organizations.find((item) => item.organizationId === selectedId);
  const canAdmin = selected && ["OWNER", "ADMIN"].includes(selected.role);

  return (
    <section className={styles.page}>
      {!embedded && (
        <header className="page-header">
          <div><span className="eyebrow">IDENTITY & TENANCY</span><h1>账户与组织</h1>
            <p>创建组织、邀请成员、切换租户和管理最小权限角色。租户选择只是选择器，授权以控制面数据库为准。</p></div>
        </header>
      )}

      {feedback && <div className={styles.feedback} role="status">{feedback}</div>}

      <div className={styles.grid}>
        <article className={styles.panel}>
          <h2>我的组织</h2>
          <label><span>组织</span>
            <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              {organizations.map((organization) => (
                <option value={organization.organizationId} key={organization.organizationId}>
                  {organization.displayName} · {organization.role}
                </option>
              ))}
            </select>
          </label>
          <button className="button primary" type="button" disabled={!selectedId || busy}
            onClick={switchOrganization}>设为当前组织</button>
          <form onSubmit={createOrganization}>
            <h3>创建组织</h3>
            <label><span>名称</span><input required minLength={2} maxLength={128}
              value={name} onChange={(event) => setName(event.target.value)} /></label>
            <label><span>数据区域</span><select value={region}
              onChange={(event) => setRegion(event.target.value)}>
              <option value="cn-north">中国北区</option>
              <option value="ap-southeast">亚太东南</option>
              <option value="eu-central">欧洲中部</option>
            </select></label>
            <button className="button" disabled={busy}>创建</button>
          </form>
        </article>

        <article className={styles.panel}>
          <h2>接受邀请</h2>
          <form onSubmit={acceptInvitation}>
            <label><span>一次性邀请令牌</span><textarea required rows={4}
              value={acceptToken} onChange={(event) => setAcceptToken(event.target.value)} /></label>
            <button className="button" disabled={busy}>验证并加入</button>
          </form>
          {canAdmin && <form onSubmit={invite}>
            <h3>邀请成员</h3>
            <label><span>已验证邮箱</span><input type="email" required
              value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} /></label>
            <label><span>角色</span><select value={inviteRole}
              onChange={(event) => setInviteRole(event.target.value)}>
              {["ADMIN", "MAINTAINER", "MEMBER", "BILLING", "VIEWER"].map((role) =>
                <option value={role} key={role}>{role}</option>)}
            </select></label>
            <button className="button" disabled={busy || !selectedId}>创建邀请</button>
          </form>}
          {invitationToken && <div className={styles.token}>
            <strong>仅显示一次</strong><code>{invitationToken}</code>
            <small>邮件/SMS 提供商未配置前，不会自动发送；外部投递证据保持 NOT_RUN。</small>
          </div>}
        </article>
      </div>

      <article className={styles.members}>
        <div><h2>成员</h2><small>{selected?.displayName ?? "未选择组织"}</small></div>
        <div className={styles.memberList}>
          {members.map((member) => (
            <div className={styles.member} key={member.accountId}>
              <div><strong>{member.displayName}</strong>
                <small>{member.accountId} · {member.state}</small></div>
              <select value={member.role} disabled={!canAdmin || busy}
                onChange={(event) => updateMember(member, event.target.value)}>
                {["OWNER", "ADMIN", "MAINTAINER", "MEMBER", "BILLING", "VIEWER"].map((role) =>
                  <option value={role} key={role}>{role}</option>)}
              </select>
              <button className="button ghost" type="button" disabled={!canAdmin || busy}
                onClick={() => removeMember(member)}>移除</button>
            </div>
          ))}
          {members.length === 0 && <p>暂无可见成员。</p>}
        </div>
      </article>
    </section>
  );
}
