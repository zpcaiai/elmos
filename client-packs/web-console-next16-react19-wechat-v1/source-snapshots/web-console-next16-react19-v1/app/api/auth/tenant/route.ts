import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  AccountSessionError,
  accountSessionErrorResponse,
  accountSessionFromRequest,
  databaseTenantMembership,
  selectDatabaseTenantCookie,
  selectTenantCookie,
  sessionCookieMaxAge,
} from "../../../lib/server/accountSession";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type OrganizationGrant = {
  organizationId: string;
  role: string;
};

function controlPlaneBaseUrl(): string {
  const configured = process.env.ELMOS_CONTROL_PLANE_BASE_URL?.trim() ?? "";
  const parsed = new URL(configured);
  const localDevelopment = process.env.NODE_ENV !== "production"
    && ["localhost", "127.0.0.1"].includes(parsed.hostname);
  if (
    (parsed.protocol !== "https:" && !(localDevelopment && parsed.protocol === "http:"))
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
  ) {
    throw new AccountSessionError(
      503,
      "CONTROL_PLANE_CONFIGURATION_INVALID",
      "控制面地址配置无效。",
    );
  }
  return parsed.toString().replace(/\/$/, "");
}

export async function POST(request: NextRequest) {
  try {
    const session = accountSessionFromRequest(request);
    const body = await request.json() as { organizationId?: unknown };
    if (typeof body.organizationId !== "string") {
      return NextResponse.json(
        { errorCode: "TENANT_SELECTION_INVALID", message: "租户选择无效。" },
        { status: 400 },
      );
    }
    const embedded = session.principal.memberships.find(
      (membership) => membership.organizationId === body.organizationId,
    );
    let sealedTenant: string;
    if (embedded) {
      sealedTenant = selectTenantCookie(
        session.principal, body.organizationId, session.expiresAt,
      );
    } else {
      const controlResponse = await fetch(
        `${controlPlaneBaseUrl()}/api/v1/account/organizations`,
        {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
            Accept: "application/json",
          },
          cache: "no-store",
          signal: AbortSignal.timeout(10_000),
        },
      );
      if (!controlResponse.ok) {
        throw new AccountSessionError(
          controlResponse.status,
          "TENANT_MEMBERSHIP_LOOKUP_REJECTED",
          "控制面未确认该组织成员关系。",
        );
      }
      const payload = await controlResponse.json() as {
        organizations?: OrganizationGrant[];
      };
      const grant = payload.organizations?.find(
        (organization) => organization.organizationId === body.organizationId,
      );
      if (!grant) {
        throw new AccountSessionError(
          403,
          "CROSS_TENANT_ACCESS_DENIED",
          "当前身份无权访问所选租户。",
        );
      }
      sealedTenant = selectDatabaseTenantCookie(
        session.principal,
        databaseTenantMembership(grant.organizationId, grant.role),
        session.expiresAt,
      );
    }
    const response = NextResponse.json({ switched: true, organizationId: body.organizationId });
    response.cookies.set(
      accountCookieNames.tenant,
      sealedTenant,
      {
        httpOnly: true,
        secure: true,
        sameSite: "lax",
        path: "/",
        maxAge: sessionCookieMaxAge(session.expiresAt),
      },
    );
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    return accountSessionErrorResponse(error);
  }
}
