import { NextResponse, type NextRequest } from "next/server";
import { health } from "../../lib/server/generationRunner";
import { probeConfiguredUpstreams } from "../../lib/server/upstreamReadiness";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const probe = request.nextUrl.searchParams.get("probe") ?? "readiness";
  if (!["liveness", "readiness"].includes(probe)) {
    return NextResponse.json(
      { status: "BLOCKED", reason: "HEALTH_PROBE_INVALID" },
      { status: 400 },
    );
  }
  if (probe === "liveness") {
    return NextResponse.json(
      { status: "UP", service: "elmos-web-console", checkedAt: new Date().toISOString() },
      { headers: { "Cache-Control": "no-store" } },
    );
  }
  const [runner, dependencies] = await Promise.all([
    health(),
    probeConfiguredUpstreams(),
  ]);
  const blocked = runner.status === "BLOCKED"
    || dependencies.some((dependency) => dependency.status === "BLOCKED");
  const status = blocked ? 503 : 200;
  return NextResponse.json(
    {
      status: status === 200 ? "UP" : "BLOCKED",
      service: "elmos-web-console",
      localRunner: runner,
      dependencies,
      checkedAt: new Date().toISOString(),
    },
    { status, headers: { "Cache-Control": "no-store" } },
  );
}
