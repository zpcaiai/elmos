import { NextRequest, NextResponse } from "next/server";
import {
  authorize,
  GenerationRunnerError,
  ingestGenerationSources,
} from "../../../lib/server/generationRunner";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_MULTIPART_BYTES = 12 * 1024 * 1024;
const workspaceIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function optionalText(form: FormData, key: string, maximum: number): string | undefined {
  const value = form.get(key);
  if (value === null) return undefined;
  if (typeof value !== "string" || value.length > maximum) {
    throw new GenerationRunnerError(400, `SOURCE_${key.toUpperCase()}_INVALID`);
  }
  const normalized = value.trim();
  return normalized || undefined;
}

function skillNames(form: FormData): string[] {
  const value = optionalText(form, "skills", 2_000);
  if (!value) return [];
  return [...new Set(value.split(/[\s,，;；]+/).map((item) => item.trim()).filter(Boolean))];
}

function repositoryWorkspaceId(form: FormData): string | undefined {
  const value = optionalText(form, "repositoryWorkspaceId", 36);
  if (value && !workspaceIdPattern.test(value)) {
    throw new GenerationRunnerError(400, "SOURCE_REPOSITORY_WORKSPACE_ID_INVALID");
  }
  return value;
}

function repositoryPaths(form: FormData): string[] {
  const value = optionalText(form, "repositoryPaths", 6_000);
  if (!value) return [];
  const paths = [...new Set(value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean))];
  if (
    paths.length > 8
    || paths.some((path) => (
      path.length > 512
      || path.startsWith("/")
      || path.includes("\\")
      || path.split("/").includes("..")
      || /[\0\r\n]/.test(path)
    ))
  ) {
    throw new GenerationRunnerError(400, "SOURCE_REPOSITORY_PATHS_INVALID");
  }
  return paths;
}

export async function POST(request: NextRequest) {
  try {
    const contentType = request.headers.get("content-type") ?? "";
    if (!contentType.startsWith("multipart/form-data")) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "MULTIPART_CONTENT_TYPE_REQUIRED" },
        { status: 415 },
      );
    }
    const contentLength = request.headers.get("content-length");
    if (!contentLength) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "SOURCE_CONTENT_LENGTH_REQUIRED" },
        { status: 411 },
      );
    }
    const declaredLength = Number(contentLength);
    if (
      !Number.isFinite(declaredLength)
      || declaredLength < 0
      || declaredLength > MAX_MULTIPART_BYTES
    ) {
      return NextResponse.json(
        { status: "BLOCKED", reason: "SOURCE_MULTIPART_TOO_LARGE" },
        { status: 413 },
      );
    }
    const context = authorize(request);
    const form = await request.formData();
    const files = form.getAll("files").filter((value): value is File => value instanceof File);
    const bundle = await ingestGenerationSources(context, {
      description: optionalText(form, "description", 32_000),
      url: optionalText(form, "url", 2_000),
      skillNames: skillNames(form),
      files,
      repositoryWorkspaceId: repositoryWorkspaceId(form),
      repositoryPaths: repositoryPaths(form),
    });
    return NextResponse.json(bundle);
  } catch (error) {
    const status = error instanceof GenerationRunnerError ? error.status : 400;
    const reason = error instanceof Error ? error.message : "SOURCE_INGESTION_FAILED";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
