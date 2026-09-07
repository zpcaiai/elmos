import {
  authorizeAdmin,
  fetchRunHistoryReplay,
  proxyErrorResponse,
} from "../../../../lib/server/operationsProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * The full reconstructed history of one migration run.
 *
 * Read-only, so VIEWER is enough — the same floor as the audit export it sits
 * beside. There is deliberately no POST, PUT or DELETE here: a replay must not
 * be able to change the record it is reconstructing. That is enforced three
 * layers down by a read-only database transaction; the absence of a write verb
 * here is the outermost of those layers, not the only one.
 *
 * A run that does not exist and a run belonging to another tenant both come
 * back as 404 from upstream, and that status is forwarded unchanged. Turning
 * one of them into a 403 would confirm the id exists somewhere.
 */
export async function GET(
  request: Request,
  context: { params: Promise<{ migrationRunId: string }> },
) {
  try {
    const administrator = authorizeAdmin(request, "VIEWER");
    const { migrationRunId } = await context.params;
    const upstream = await fetchRunHistoryReplay(migrationRunId, administrator);
    const payload = await upstream.text();
    return new Response(payload, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        // Tenant-scoped and reconstructed on demand: never cached.
        "Cache-Control": "no-store, private",
        "Vary": "Authorization",
      },
    });
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
