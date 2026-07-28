import { createReadStream } from "node:fs";
import { Readable } from "node:stream";
import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../../../lib/server/generationRunner";
import {
  authorizeTranslation,
  translationArtifact,
} from "../../../../../lib/server/translationRunner";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    const authorized = authorizeTranslation(request);
    const { jobId } = await context.params;
    const artifact = await translationArtifact(authorized, jobId);
    const stream = Readable.toWeb(createReadStream(artifact.path)) as ReadableStream;
    return new NextResponse(stream, {
      headers: {
        "Content-Type": "application/zip",
        "Content-Length": String(artifact.size),
        "Content-Disposition": 'attachment; filename="repository-migration-artifact.zip"',
        "X-Content-SHA256": artifact.sha256,
        "ETag": `"sha256-${artifact.sha256}"`,
        "Cache-Control": "private, no-store",
      },
    });
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "TRANSLATION_RUNNER_ERROR";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
