import { NextResponse } from "next/server";
import { directedLanguageRoutes, translationLanguages } from "../../../lib/businessLines";
import type { TranslationCapabilityResponse } from "../../../lib/contracts";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json<TranslationCapabilityResponse>({
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date().toISOString(),
    schemaVersion: "1.1.0",
    languages: translationLanguages,
    routes: directedLanguageRoutes,
    routePackageCount: 12,
    repositoryPlanning: "LOCAL_MANIFEST_SUPPORTED",
    localExecutionEvidence: "PASSED_LOCAL",
    externalExecutionEvidence: "NOT_RUN",
    certificationStatus: "NOT_CERTIFIED",
    note: "12 条路线的 typed-pure-function-v1 已用精确本地工具链完成开发、holdout 与代表性语料的编译和行为回放；整库可生成内容寻址的只读清单与工作单元，但转换执行、独立验证与外部认证仍须逐单元完成。",
  });
}
