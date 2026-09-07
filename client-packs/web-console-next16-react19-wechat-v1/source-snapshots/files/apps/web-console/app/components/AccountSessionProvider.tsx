"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type AccountSessionPrincipal = {
  actorId: string;
  displayName: string;
  email?: string;
  organizationId: string;
  roles: string[];
  permissions: string[];
  memberships: Array<{
    organizationId: string;
    roles: string[];
    permissions: string[];
  }>;
};

type AccountSessionState = {
  status: "loading" | "authenticated" | "anonymous" | "not-configured";
  principal: AccountSessionPrincipal | null;
  expiresAt: string | null;
  refresh: () => Promise<void>;
  switchTenant: (organizationId: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AccountSessionContext = createContext<AccountSessionState | null>(null);
const channelName = "elmos-account-session-v1";

type SessionResponse = {
  authenticated: boolean;
  configured: boolean;
  principal: AccountSessionPrincipal | null;
  expiresAt: string | null;
};

async function readSession(): Promise<SessionResponse> {
  const response = await fetch("/api/auth/session", {
    credentials: "same-origin",
    cache: "no-store",
  });
  const payload = await response.json() as SessionResponse;
  return payload;
}

export function AccountSessionProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AccountSessionState["status"]>("loading");
  const [principal, setPrincipal] = useState<AccountSessionPrincipal | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);

  const apply = useCallback((payload: SessionResponse) => {
    setPrincipal(payload.principal);
    setExpiresAt(payload.expiresAt);
    setStatus(payload.authenticated
      ? "authenticated"
      : payload.configured
        ? "anonymous"
        : "not-configured");
  }, []);

  const refresh = useCallback(async () => {
    try {
      apply(await readSession());
    } catch {
      setPrincipal(null);
      setExpiresAt(null);
      setStatus("anonymous");
    }
  }, [apply]);

  useEffect(() => {
    void refresh();
    const channel = typeof BroadcastChannel === "undefined"
      ? null
      : new BroadcastChannel(channelName);
    const update = () => void refresh();
    channel?.addEventListener("message", update);
    window.addEventListener("storage", update);
    return () => {
      channel?.removeEventListener("message", update);
      channel?.close();
      window.removeEventListener("storage", update);
    };
  }, [refresh]);

  useEffect(() => {
    if (!expiresAt || status !== "authenticated") return;
    const expiry = Date.parse(expiresAt);
    const delay = Math.max(15_000, Math.min(5 * 60_000, expiry - Date.now() - 2 * 60_000));
    const timer = window.setTimeout(async () => {
      const response = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
      });
      if (response.ok) {
        await refresh();
      } else {
        setPrincipal(null);
        setExpiresAt(null);
        setStatus("anonymous");
      }
    }, delay);
    return () => window.clearTimeout(timer);
  }, [expiresAt, refresh, status]);

  const switchTenant = useCallback(async (organizationId: string) => {
    const response = await fetch("/api/auth/tenant", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ organizationId }),
    });
    if (!response.ok) throw new Error("TENANT_SWITCH_REJECTED");
    await refresh();
    localStorage.setItem("elmos:account-session-updated", String(Date.now()));
    if (typeof BroadcastChannel !== "undefined") {
      const channel = new BroadcastChannel(channelName);
      channel.postMessage("tenant-switched");
      channel.close();
    }
  }, [refresh]);

  const logout = useCallback(async () => {
    const response = await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
    });
    const payload = await response.json() as { endSessionUrl?: string | null };
    setPrincipal(null);
    setExpiresAt(null);
    setStatus("anonymous");
    localStorage.setItem("elmos:account-session-updated", String(Date.now()));
    if (typeof BroadcastChannel !== "undefined") {
      const channel = new BroadcastChannel(channelName);
      channel.postMessage("logout");
      channel.close();
    }
    if (payload.endSessionUrl) window.location.assign(payload.endSessionUrl);
    else window.location.assign("/login");
  }, []);

  const value = useMemo<AccountSessionState>(() => ({
    status,
    principal,
    expiresAt,
    refresh,
    switchTenant,
    logout,
  }), [expiresAt, logout, principal, refresh, status, switchTenant]);

  return (
    <AccountSessionContext.Provider value={value}>
      {children}
    </AccountSessionContext.Provider>
  );
}

export function useAccountSession(): AccountSessionState {
  const value = useContext(AccountSessionContext);
  if (!value) throw new Error("AccountSessionProvider is required");
  return value;
}
