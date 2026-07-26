import { NextResponse, type NextRequest } from "next/server";
import { health } from "../../lib/server/generationRunner";

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
  const runner = await health();
  const status = runner.status === "BLOCKED" ? 503 : 200;
  return NextResponse.json(
    {
      status: status === 200 ? "UP" : "BLOCKED",
      service: "elmos-web-console",
      localRunner: runner,
    },
    { status, headers: { "Cache-Control": "no-store" } },
  );
}
