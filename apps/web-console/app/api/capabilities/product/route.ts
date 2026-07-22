import { NextResponse } from "next/server";
import { productStages } from "../../../lib/catalog";
import type { ProductCapabilityResponse } from "../../../lib/contracts";

export const dynamic = "force-dynamic";

type LiveCapabilities = {
  namespace?: string;
  decisionCeiling?: string;
  externalExecutionEvidence?: string;
};

export async function GET() {
  const baseUrl = process.env.CONTROL_PLANE_BASE_URL ?? "http://127.0.0.1:8080";
  const fallback: ProductCapabilityResponse = {
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date().toISOString(),
    namespace: "Product Batch B34-B38",
    decisionCeiling: "READY_FOR_EXTERNAL_GATE_OR_HUMAN_DECISION",
    externalExecutionEvidence: "NOT_RUN",
    stages: productStages,
    note: "控制面未连接；显示仓库契约。页面不会伪造运行回执。",
  };

  try {
    const response = await fetch(`${baseUrl}/api/v1/product-commercialization/capabilities`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1600),
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return NextResponse.json(fallback);
    const live = await response.json() as LiveCapabilities;
    return NextResponse.json<ProductCapabilityResponse>({
      ...fallback,
      source: "LIVE_API",
      namespace: live.namespace ?? fallback.namespace,
      decisionCeiling: live.decisionCeiling ?? fallback.decisionCeiling,
      note: "能力边界已从本地控制面读取；外部执行证据仍保持 NOT_RUN。",
    });
  } catch {
    return NextResponse.json(fallback);
  }
}
