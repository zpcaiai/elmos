import { NextRequest, NextResponse } from "next/server";
import { authorizeTranslation, translationRunnerHealth } from "../../../lib/server/translationRunner";
import { call, hostedExecutionEnabled } from "../../../lib/server/hostedExecutionClient";
import { GenerationRunnerError } from "../../../lib/server/generationRunner";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (hostedExecutionEnabled()) {
    try {
      const result=await call(authorizeTranslation(request),"/api/v1/execution/jobs/translation-readiness","GET");
      return NextResponse.json(result,{headers:{"Cache-Control":"private, no-store"}});
    } catch (error) {
      return NextResponse.json({status:"BLOCKED",isolation:"NOT_CONFIGURED",sourceStorage:"NOT_RUN",
        reason:error instanceof GenerationRunnerError ? error.code : "TRANSLATION_HOSTED_CONFIGURATION_REQUIRED"},
        {status:error instanceof GenerationRunnerError ? error.status : 503,headers:{"Cache-Control":"private, no-store"}});
    }
  }
  const result = await translationRunnerHealth();
  return NextResponse.json(result, {
    status: result.status === "READY" || result.status === "DISABLED" ? 200 : 503,
    headers: { "cache-control": "no-store" },
  });
}
