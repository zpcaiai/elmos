import { NextResponse, type NextRequest } from "next/server";
import { translationLanguages } from "../../../lib/businessLines";
import type { TranslationLanguageId } from "../../../lib/contracts";
import {
  MAX_DISCOVERY_BYTES,
  validateDiscoveryReport,
} from "../../../lib/server/translationDiscovery";
import { RepositoryPlanError, isSafeRepositoryRef } from "../../../lib/server/translationRepositoryPlan";

export const dynamic = "force-dynamic";

const languageIds = new Set<string>(translationLanguages.map((language) => language.id));
const SHA256 = /^[0-9a-f]{64}$/;

function blocked(errorCode: string, message: string, status = 422) {
  return NextResponse.json(
    { status: "BLOCKED", errorCode, message },
    { status, headers: { "cache-control": "no-store" } },
  );
}

export async function POST(request: NextRequest) {
  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(contentLength) && contentLength > MAX_DISCOVERY_BYTES) {
    return blocked("DISCOVERY_TOO_LARGE", "发现报告超过 8 MB 上限，请缩小评估范围。", 413);
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return blocked("DISCOVERY_BODY_UNPARSEABLE", "请求体不是合法 JSON。", 400);
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return blocked("DISCOVERY_BODY_INVALID", "请求体顶层不是对象。", 400);
  }

  const payload = body as Record<string, unknown>;
  const repositoryRef = typeof payload.repositoryRef === "string" ? payload.repositoryRef.trim() : "";
  const routeId = typeof payload.routeId === "string" ? payload.routeId : "";
  const snapshotSha256 = typeof payload.snapshotSha256 === "string" ? payload.snapshotSha256 : "";
  const sourceLanguage = typeof payload.sourceLanguage === "string" ? payload.sourceLanguage : "";
  const targetLanguage = typeof payload.targetLanguage === "string" ? payload.targetLanguage : "";

  if (!isSafeRepositoryRef(repositoryRef)) {
    return blocked("REPOSITORY_REF_INVALID", "仓库引用不安全。", 400);
  }
  if (!SHA256.test(snapshotSha256)) {
    return blocked("SNAPSHOT_REQUIRED", "必须先导入整库清单并提供其 Snapshot 摘要。", 400);
  }
  if (!languageIds.has(sourceLanguage) || !languageIds.has(targetLanguage)) {
    return blocked("LANGUAGE_UNSUPPORTED", "源语言或目标语言不在受支持列表中。", 400);
  }
  if (routeId !== `${sourceLanguage}-to-${targetLanguage}`) {
    return blocked("ROUTE_ID_MISMATCH", "路线标识与源/目标语言不一致。", 400);
  }

  try {
    const report = validateDiscoveryReport(payload.report, {
      repositoryRef,
      routeId,
      snapshotSha256,
      sourceLanguage: sourceLanguage as TranslationLanguageId,
      targetLanguage: targetLanguage as TranslationLanguageId,
    });
    return NextResponse.json(
      { status: "ACCEPTED", executionStatus: "NOT_RUN", report },
      { headers: { "cache-control": "no-store" } },
    );
  } catch (error) {
    if (error instanceof RepositoryPlanError) {
      return blocked(error.errorCode, error.message);
    }
    return blocked("DISCOVERY_VALIDATION_FAILED", "发现报告校验失败。", 500);
  }
}
