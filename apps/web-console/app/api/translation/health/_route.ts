import { NextResponse } from "next/server";
import { translationRunnerHealth } from "../../../lib/server/translationRunner";

export const dynamic = "force-dynamic";

export async function GET() {
  const result = await translationRunnerHealth();
  return NextResponse.json(result, {
    status: result.status === "READY" || result.status === "DISABLED" ? 200 : 503,
    headers: { "cache-control": "no-store" },
  });
}
