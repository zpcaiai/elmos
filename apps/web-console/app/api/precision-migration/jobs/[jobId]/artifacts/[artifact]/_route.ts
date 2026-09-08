import { NextRequest, NextResponse } from "next/server";

import {
  precisionContext,
  PrecisionMigrationRunnerError,
  readPrecisionArtifact,
} from "../../../../../../lib/server/precisionMigrationRunner";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string; artifact: string }> },
) {
  try {
    const { jobId, artifact } = await context.params;
    const result = await readPrecisionArtifact(precisionContext(request), jobId, artifact);
    return new NextResponse(new Uint8Array(result.content), {
      headers: {
        "content-type": result.mediaType,
        "content-disposition": `attachment; filename="${result.fileName}"`,
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      },
    });
  } catch (error) {
    const status = error instanceof PrecisionMigrationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "PRECISION_RUNNER_FAILED";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
