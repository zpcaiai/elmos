import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import {
  AccountSessionError,
  accountSessionFromRequest,
  isPlatformAdministrator,
} from "../lib/server/accountSession";
import { OperationsAdmin } from "./OperationsAdmin";

export const metadata: Metadata = {
  title: "运营管理端",
  description: "ELMOS 用户操作、性能与错误观测管理端",
};

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const requestHeaders = new Headers(await headers());
  let denialCode: string | null = null;
  try {
    const session = accountSessionFromRequest(
      new Request("https://elmos.invalid/admin", { headers: requestHeaders }),
      "admin:read",
    );
    if (!isPlatformAdministrator(session.principal)) {
      denialCode = "ADMIN_EMAIL_REQUIRED";
    }
  } catch (error) {
    denialCode = error instanceof AccountSessionError
      ? error.code
      : "ADMIN_SESSION_REQUIRED";
  }
  if (denialCode) {
    redirect(`/admin/login?${new URLSearchParams({ error: denialCode })}`);
  }
  return <OperationsAdmin />;
}
