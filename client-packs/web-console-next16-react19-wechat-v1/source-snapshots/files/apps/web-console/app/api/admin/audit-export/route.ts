import {
  authorizeAdmin,
  fetchAuditExport,
  proxyErrorResponse,
} from "../../../lib/server/operationsProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * One keyset page of the audit trail.
 *
 * Read-only, so VIEWER is enough — the same floor the operations console
 * itself sits behind. There is deliberately no POST here: an export must never
 * be able to change the record it is exporting.
 */
export async function GET(request: Request) {
  try {
    const administrator = authorizeAdmin(request, "VIEWER");
    const upstream = await fetchAuditExport(
      new URL(request.url).searchParams,
      administrator,
    );
    const payload = await upstream.text();
    return new Response(payload, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        // An audit page must never be cached: it is tenant-scoped and the
        // window is relative to now.
        "Cache-Control": "no-store, private",
        "Vary": "Authorization",
      },
    });
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
