import { NextResponse } from "next/server";
import { generationStages, generationTargets } from "../../../lib/catalog";
import type { GenerationCapabilityResponse } from "../../../lib/contracts";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json<GenerationCapabilityResponse>({
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date().toISOString(),
    schemaVersion: "1.0.0",
    projectSkillCount: 170,
    targets: generationTargets,
    stages: generationStages,
    generationStatus: "NOT_RUN",
    externalExecutionEvidence: "NOT_RUN",
    productionDeliveryStatus: "NOT_RUN",
    certificationStatus: "NOT_CERTIFIED",
    note: "目标与流程来自仓库内 Project Synthesis 1.0.0 契约；页面只准备受控 CLI 交接，不会在服务器或浏览器中执行生成器。",
  });
}
