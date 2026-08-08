import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../lib/server/generationRunner";
import { authorizeSmoke, smokeCapability } from "../../../lib/server/smokeLeaseRunner";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    authorizeSmoke(request);
    return NextResponse.json(smokeCapability());
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "SMOKE_CAPABILITY_UNAVAILABLE";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
