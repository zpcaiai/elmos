import { Readable } from "node:stream";
import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../../../lib/server/generationRunner";
import {
  authorizeTranslation,
  translationReport,
} from "../../../../../lib/server/translationRunner";

export const dynamic = "force-dynamic";

const privateHeaders = { "Cache-Control": "private, no-store" };

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  let openReport: Awaited<ReturnType<typeof translationReport>> | undefined;
  try {
    const queryKeys = [...request.nextUrl.searchParams.keys()];
    const formats = request.nextUrl.searchParams.getAll("format");
    if (queryKeys.some((key) => key !== "format") || formats.length > 1) {
      throw new GenerationRunnerError(400, "TRANSLATION_REPORT_FORMAT_INVALID");
    }
    const requested = formats[0] ?? "markdown";
    if (requested !== "markdown" && requested !== "json" && requested !== "bundle") {
      throw new GenerationRunnerError(400, "TRANSLATION_REPORT_FORMAT_INVALID");
    }
    const authorized = authorizeTranslation(request);
    const { jobId } = await context.params;
    const report = await translationReport(authorized, jobId, requested);
    const markdown = requested === "markdown";
    const bundle = requested === "bundle";
    openReport = report;
    const stream = Readable.toWeb(
      report.handle.createReadStream({ start: 0, autoClose: true }),
    ) as ReadableStream;
    return new NextResponse(stream, {
      headers: {
        ...privateHeaders,
        "Content-Type": bundle
          ? "application/zip"
          : markdown ? "text/markdown; charset=utf-8" : "application/json; charset=utf-8",
        "Content-Length": String(report.size),
        "Content-Disposition": bundle
          ? 'attachment; filename="FUNCTION_CONVERSION_REPORT_BUNDLE.zip"'
          : markdown
            ? 'attachment; filename="FUNCTION_CONVERSION_REPORT.md"'
            : 'attachment; filename="functional-conversion-report.json"',
        "X-Content-SHA256": report.sha256,
        "X-Content-Type-Options": "nosniff",
        ETag: `"sha256-${report.sha256}"`,
      },
    });
  } catch (error) {
    await openReport?.handle.close().catch(() => undefined);
    const status = error instanceof GenerationRunnerError ? error.status : 500;
    const reason = error instanceof GenerationRunnerError
      ? error.message
      : "TRANSLATION_RUNNER_ERROR";
    return NextResponse.json(
      { status: "BLOCKED", reason },
      { status, headers: privateHeaders },
    );
  }
}
