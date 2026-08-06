import {
  adjustTenantQuota,
  authorizeAdmin,
  fetchTenantQuota,
  proxyErrorResponse,
} from "../../../lib/server/operationsProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Tenant-scoped commercial state: never cached, and never shared between principals. */
const HEADERS = {
  "Cache-Control": "no-store, private",
  Vary: "Authorization",
} as const;

/**
 * Reads the tenant's current allowance.
 *
 * VIEWER, because seeing what a tenant is entitled to is the same class of read
 * as seeing what it has used — both already appear on the operations console.
 */
export async function GET(request: Request) {
  try {
    const administrator = authorizeAdmin(request, "VIEWER");
    const upstream = await fetchTenantQuota(administrator);
    const payload = await upstream.text();
    return new Response(payload, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        ...HEADERS,
      },
    });
  } catch (error) {
    return proxyErrorResponse(error);
  }
}

/**
 * Changes the allowance. APPROVER, not OPERATOR.
 *
 * Raising a limit spends money and lowering one can halt work a tenant has
 * already been told it may perform, so this sits at the same level as approving
 * a remediation rather than at the level of acknowledging an alert. The two
 * verbs on this route deliberately carry different floors: putting the read at
 * APPROVER too would have pushed operators to share an approver credential just
 * to look at a number.
 *
 * The 409 that comes back on a version mismatch is forwarded unchanged. It means
 * someone else changed the allowance since this screen was drawn, and the
 * operator has to re-read before deciding again — collapsing it into a retry
 * here would apply their intent on top of a change they never saw.
 */
export async function POST(request: Request) {
  try {
    const administrator = authorizeAdmin(request, "APPROVER");
    const body = await request.json();
    const upstream = await adjustTenantQuota(body, administrator);
    const payload = await upstream.text();
    return new Response(payload, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        ...HEADERS,
      },
    });
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
