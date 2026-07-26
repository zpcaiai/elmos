import { NextResponse } from "next/server";
import { generationStages, generationTargets } from "../../../lib/catalog";
import type { GenerationCapabilityResponse } from "../../../lib/contracts";
import { capability } from "../../../lib/server/generationRunner";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json<GenerationCapabilityResponse>({
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date().toISOString(),
    schemaVersion: "1.1.0",
    projectSkillCount: 417,
    targets: generationTargets,
    stages: generationStages,
    generationStatus: "NOT_RUN",
    externalExecutionEvidence: "NOT_RUN",
    productionDeliveryStatus: "NOT_RUN",
    certificationStatus: "NOT_CERTIFIED",
    localRunner: capability(),
    note: "8 个目标来自 Project Synthesis 1.2.0 引擎契约；本地 Runner 默认关闭，生产模式要求 rootless 容器、内部无外网网络、只读文件系统与资源限额。短期 Bearer 凭证必须绑定精确租户和 Actor，审阅摘要必须与执行输入一致。",
  });
}
