import {
  authorizeAdmin,
  fetchActivitySummary,
  proxyErrorResponse,
} from "../../../lib/server/operationsProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    authorizeAdmin(request.headers.get("authorization"));
    const upstream = await fetchActivitySummary(new URL(request.url).searchParams);
    const payload = await upstream.text();
    return new Response(payload, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store, private",
        "Vary": "Authorization",
      },
    });
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
