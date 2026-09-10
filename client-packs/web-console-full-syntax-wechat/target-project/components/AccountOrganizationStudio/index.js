Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    embedded: {
      type: null,
      value: "false",
    },
  },
  data: {
    organizations: [],
    selectedId: "",
    members: [],
    name: "",
    region: "cn-north",
    inviteEmail: "",
    inviteRole: "MEMBER",
    invitationToken: "",
    acceptToken: "",
    feedback: "",
    busy: false,
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_1
      try {
        if (account.status !== "authenticated") return;
    void loadOrganizations().catch((error: unknown) =>
      setFeedback(error instanceof Error ? error.message : "ACCOUNT_LOAD_FAILED"));
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_2
      try {
        void loadMembers(selectedId).catch((error: unknown) =>
      setFeedback(error instanceof Error ? error.message : "MEMBER_LOAD_FAILED"));
      } catch (err) {
        console.error("Effect execution error:", err);
      }
    },
    detached() {
    },
  },
  methods: {
    run(action) {
      setBusy(true);
    setFeedback("");
    try {
        await action();
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "ACCOUNT_REQUEST_REJECTED");
    }
    finally {
        setBusy(false);
    }
    },
    createOrganization(event) {
      event.preventDefault();
    void run(async () => {
        const created = await call("organizations", {
            method: "POST",
            body: JSON.stringify({ displayName: name, dataRegion: region }),
        });
        setName("");
        await loadOrganizations();
        setSelectedId(created.organizationId);
        setFeedback("组织已创建；成员关系已立即写入租户目录。");
    });
    },
    invite(event) {
      event.preventDefault();
    void run(async () => {
        const result = await call(`organizations/${encodeURIComponent(selectedId)}/invitations`, {
            method: "POST",
            body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
        });
        setInvitationToken(result.invitationToken);
        setInviteEmail("");
        setFeedback("邀请已创建。请通过已批准的安全渠道发送一次性令牌。");
    });
    },
    acceptInvitation(event) {
      event.preventDefault();
    void run(async () => {
        const result = await call("invitations/accept", {
            method: "POST",
            body: JSON.stringify({ token: acceptToken }),
        });
        setAcceptToken("");
        await loadOrganizations();
        setSelectedId(result.organizationId);
        setFeedback("邀请已接受，组织访问已生效。");
    });
    },
    switchOrganization() {
      void run(async () => {
        await account.switchTenant(selectedId);
        setFeedback("当前组织已切换；后续控制面请求会再次验证成员关系。");
    });
    },
    updateMember(member, role) {
      void run(async () => {
        await call(`organizations/${encodeURIComponent(selectedId)}/members/${encodeURIComponent(member.accountId)}`, { method: "PATCH", body: JSON.stringify({ role }) });
        await loadMembers(selectedId);
        setFeedback("成员角色已更新。");
    });
    },
    removeMember(member) {
      void run(async () => {
        await call(`organizations/${encodeURIComponent(selectedId)}/members/${encodeURIComponent(member.accountId)}`, { method: "DELETE" });
        await loadMembers(selectedId);
        setFeedback("成员已移除；最后一位 Owner 受数据库保护，不能被移除。");
    });
    },
  },
});
