import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../lib/server/generationRunner";
import { authorizeSmoke, smokePackSummary } from "../../../lib/server/smokeLeaseRunner";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    authorizeSmoke(request);
    const projectRef = request.nextUrl.searchParams.get("projectRef") ?? "";
    return NextResponse.json(await smokePackSummary(projectRef));
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "SMOKE_PACK_UNAVAILABLE";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
