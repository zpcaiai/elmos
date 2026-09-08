import { NextResponse } from "next/server";
import { generationStages, generationTargets } from "../../../lib/catalog";
import type { GenerationCapabilityResponse } from "../../../lib/contracts";
import { generationDeploymentGuidance } from "../../../lib/deploymentGuidance";
import { aggregateGenerationReadiness } from "../../../lib/server/generationReadiness";
import { capability, health } from "../../../lib/server/generationRunner";
import { probeConfiguredUpstreams } from "../../../lib/server/upstreamReadiness";

export const dynamic = "force-dynamic";

export async function GET() {
  const [runnerHealth, dependencies] = await Promise.all([
    health(),
    probeConfiguredUpstreams(),
  ]);
  const operationalReadiness = aggregateGenerationReadiness({
    localRunner: runnerHealth,
    dependencies,
  });
  return NextResponse.json<GenerationCapabilityResponse>({
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date().toISOString(),
    schemaVersion: "1.1.0",
    projectSkillCount: 417,
    targets: generationTargets,
    stages: generationStages,
    generationStatus: operationalReadiness.status,
    externalExecutionEvidence: "NOT_RUN",
    productionDeliveryStatus: "NOT_RUN",
    certificationStatus: "NOT_CERTIFIED",
    localRunner: capability(),
    operationalReadiness,
    deploymentGuidance: generationDeploymentGuidance(),
    note: "8 个目标来自 Project Synthesis 1.4.0 引擎契约；本地 Runner 默认关闭，生产模式要求 rootless 容器、内部无外网网络、只读文件系统与资源限额。生产服务凭证必须短期、单次使用，并绑定精确租户、Actor、权限、方法、路径与受众；审阅摘要必须与执行输入一致。",
  });
}
