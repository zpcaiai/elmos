import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../../lib/server/generationRunner";
import { authorizeSmoke, readSmokeSession } from "../../../../lib/server/smokeLeaseRunner";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  try {
    const authorized = authorizeSmoke(request);
    const { sessionId } = await context.params;
    return NextResponse.json(await readSmokeSession(authorized, sessionId));
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "SMOKE_SESSION_UNAVAILABLE";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
