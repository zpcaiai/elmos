import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  unsafeCookieValue,
} from "../../../../../lib/server/accountSession";
import {
  GenerationGitHubPublishError,
  publishGenerationToGitHub,
  type GenerationGitHubPublishRequest,
} from "../../../../../lib/server/generationGitHubPublisher";
import {
  authorize,
  GenerationRunnerError,
} from "../../../../../lib/server/generationRunner";
import { hostedExecutionEnabled } from "../../../../../lib/server/hostedExecutionClient";
import { withBusinessAudit } from "../../../../../lib/server/operationsProxy";

export const dynamic = "force-dynamic";
const maximumRequestBytes = 8 * 1024;

async function readRequestTextBounded(request: Request): Promise<string> {
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Buffer[] = [];
  let byteLength = 0;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      byteLength += next.value.byteLength;
      if (byteLength > maximumRequestBytes) {
        await reader.cancel().catch(() => undefined);
        throw new GenerationGitHubPublishError(413, "REQUEST_TOO_LARGE");
      }
      chunks.push(Buffer.from(next.value));
    }
  } catch (error) {
    if (error instanceof GenerationGitHubPublishError) throw error;
    throw new GenerationGitHubPublishError(400, "REQUEST_BODY_INVALID");
  } finally {
    reader.releaseLock();
  }
  return Buffer.concat(chunks, byteLength).toString("utf-8");
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    return await withBusinessAudit(
      request,
      {
        action: "GENERATION_GITHUB_PRIVATE_REPOSITORY_PUBLISH",
        businessLine: "PROJECT_SYNTHESIS",
        route: "/api/generation/jobs/:id/github",
        target: "generation-github-private-repository",
      },
      () => publish(request, context),
    );
  } catch {
    return NextResponse.json(
      { status: "BLOCKED", reason: "BUSINESS_AUDIT_UNAVAILABLE" },
      { status: 503, headers: { "Cache-Control": "private, no-store" } },
    );
  }
}

async function publish(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    const authorized = authorize(request, "repository:push");
    const hasAccountSession = Boolean(
      unsafeCookieValue(request, accountCookieNames.session),
    );
    if (
      !hasAccountSession
      && (
        process.env.NODE_ENV === "production"
        || process.env.ELMOS_LOCAL_GITHUB_PUBLISH_ENABLED !== "true"
      )
    ) throw new GenerationGitHubPublishError(403, "LOCAL_GITHUB_PUBLISH_NOT_ENABLED");
    if (hostedExecutionEnabled()) {
      throw new GenerationGitHubPublishError(
        501,
        "GITHUB_PUBLISH_HOSTED_EXECUTION_NOT_RUN",
      );
    }
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "JSON_CONTENT_TYPE_REQUIRED" },
        { status: 415 },
      );
    }
    const declaredLength = request.headers.get("content-length");
    if (declaredLength !== null) {
      if (!/^\d{1,7}$/.test(declaredLength)) {
        return NextResponse.json(
          { status: "BLOCKED", reason: "CONTENT_LENGTH_INVALID" },
          { status: 400 },
        );
      }
      if (Number(declaredLength) > maximumRequestBytes) {
        return NextResponse.json(
          { status: "BLOCKED", reason: "REQUEST_TOO_LARGE" },
          { status: 413 },
        );
      }
    }
    const rawBody = await readRequestTextBounded(request);
    const { jobId } = await context.params;
    let body: GenerationGitHubPublishRequest;
    try {
      body = JSON.parse(rawBody) as GenerationGitHubPublishRequest;
    } catch {
      throw new GenerationGitHubPublishError(400, "JSON_BODY_INVALID");
    }
    return NextResponse.json(await publishGenerationToGitHub(authorized, jobId, body), {
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch (error) {
    const status = error instanceof GenerationGitHubPublishError
      || error instanceof GenerationRunnerError
      ? error.status
      : 500;
    const reason = error instanceof GenerationGitHubPublishError
      || error instanceof GenerationRunnerError
      ? error.code
      : "GITHUB_PUBLICATION_FAILED";
    return NextResponse.json(
      { status: "BLOCKED", reason },
      { status, headers: { "Cache-Control": "private, no-store" } },
    );
  }
}
