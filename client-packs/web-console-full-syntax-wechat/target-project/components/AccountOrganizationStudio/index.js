Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    embedded: {
      type: null,
      value: false,
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
      const setOrganizations = (val) => { this.setData({ organizations: typeof val === "function" ? val(this.data.organizations) : val }); };
      const setSelectedId = (val) => { this.setData({ selectedId: typeof val === "function" ? val(this.data.selectedId) : val }); };
      const setMembers = (val) => { this.setData({ members: typeof val === "function" ? val(this.data.members) : val }); };
      const setName = (val) => { this.setData({ name: typeof val === "function" ? val(this.data.name) : val }); };
      const setRegion = (val) => { this.setData({ region: typeof val === "function" ? val(this.data.region) : val }); };
      const setInviteEmail = (val) => { this.setData({ inviteEmail: typeof val === "function" ? val(this.data.inviteEmail) : val }); };
      const setInviteRole = (val) => { this.setData({ inviteRole: typeof val === "function" ? val(this.data.inviteRole) : val }); };
      const setInvitationToken = (val) => { this.setData({ invitationToken: typeof val === "function" ? val(this.data.invitationToken) : val }); };
      const setAcceptToken = (val) => { this.setData({ acceptToken: typeof val === "function" ? val(this.data.acceptToken) : val }); };
      const setFeedback = (val) => { this.setData({ feedback: typeof val === "function" ? val(this.data.feedback) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          if (account.status !== "authenticated")
        return;
    void loadOrganizations().catch((error) => setFeedback(error instanceof Error ? error.message : "ACCOUNT_LOAD_FAILED"));
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          void loadMembers(selectedId).catch((error) => setFeedback(error instanceof Error ? error.message : "MEMBER_LOAD_FAILED"));
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    async run(action) {
      try {
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
      } catch (err) {
        console.warn("run execution warning:", err);
      }
    },
    async createOrganization(event) {
      try {
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
      } catch (err) {
        console.warn("createOrganization execution warning:", err);
      }
    },
    async invite(event) {
      try {
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
      } catch (err) {
        console.warn("invite execution warning:", err);
      }
    },
    async acceptInvitation(event) {
      try {
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
      } catch (err) {
        console.warn("acceptInvitation execution warning:", err);
      }
    },
    async switchOrganization() {
      try {
        void run(async () => {
        await account.switchTenant(selectedId);
        setFeedback("当前组织已切换；后续控制面请求会再次验证成员关系。");
    });
      } catch (err) {
        console.warn("switchOrganization execution warning:", err);
      }
    },
    async updateMember(member, role) {
      try {
        void run(async () => {
        await call(`organizations/${encodeURIComponent(selectedId)}/members/${encodeURIComponent(member.accountId)}`, { method: "PATCH", body: JSON.stringify({ role }) });
        await loadMembers(selectedId);
        setFeedback("成员角色已更新。");
    });
      } catch (err) {
        console.warn("updateMember execution warning:", err);
      }
    },
    async removeMember(member) {
      try {
        void run(async () => {
        await call(`organizations/${encodeURIComponent(selectedId)}/members/${encodeURIComponent(member.accountId)}`, { method: "DELETE" });
        await loadMembers(selectedId);
        setFeedback("成员已移除；最后一位 Owner 受数据库保护，不能被移除。");
    });
      } catch (err) {
        console.warn("removeMember execution warning:", err);
      }
    },
  },
});
