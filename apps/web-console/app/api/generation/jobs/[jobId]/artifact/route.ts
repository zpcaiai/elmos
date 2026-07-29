import { createReadStream } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { NextRequest, NextResponse } from "next/server";
import {
  artifact,
  authorize,
  GenerationRunnerError,
} from "../../../../../lib/server/generationRunner";
import {
  hostedArtifactTicket,
  hostedExecutionEnabled,
} from "../../../../../lib/server/hostedExecutionClient";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    const authorized = authorize(request);
    const { jobId } = await context.params;
    if (hostedExecutionEnabled()) {
      return NextResponse.json(await hostedArtifactTicket(authorized, jobId), {
        headers: { "Cache-Control": "private, no-store" },
      });
    }
    const archive = await artifact(authorized, jobId);
    const stream = Readable.toWeb(createReadStream(archive.path)) as ReadableStream;
    return new NextResponse(stream, {
      headers: {
        "Content-Type": "application/zip",
        "Content-Length": String(archive.size),
        "Content-Disposition": `attachment; filename="${path.basename(archive.path)}"`,
        "X-Content-SHA256": archive.sha256,
        "ETag": `"sha256-${archive.sha256}"`,
        "Cache-Control": "private, no-store",
      },
    });
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "RUNNER_ERROR";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
