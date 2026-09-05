import { NextResponse } from "next/server";
import { migrationCapabilities } from "../../../lib/catalog";
import type { CapabilityResponse, MigrationCapability } from "../../../lib/contracts";

export const dynamic = "force-dynamic";

type LivePack = {
  pack?: number;
  domain?: string;
  gateCommand?: string;
  skillCount?: number;
  schemaCount?: number;
};

export async function GET() {
  const baseUrl = process.env.CONTROL_PLANE_BASE_URL ?? "http://127.0.0.1:8080";
  let source: CapabilityResponse<MigrationCapability>["source"] = "REPOSITORY_CONTRACT";
  let note = "控制面未连接；显示仓库内的精确能力契约，不代表外部执行或认证。";
  let capabilities = migrationCapabilities;

  try {
    const response = await fetch(`${baseUrl}/api/v1/migration-pack-certification/capabilities`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1600),
      headers: { Accept: "application/json" },
    });
    if (response.ok) {
      const live = await response.json() as LivePack[];
      if (Array.isArray(live)) {
        capabilities = migrationCapabilities.map((fallback) => {
          const current = live.find((item) => item.pack === fallback.batch);
          return current ? {
            ...fallback,
            domain: current.domain ?? fallback.domain,
            gateCommand: current.gateCommand ?? fallback.gateCommand,
            skillCount: current.skillCount ?? fallback.skillCount,
            schemaCount: current.schemaCount ?? fallback.schemaCount,
          } : fallback;
        });
        source = "LIVE_API";
        note = "M29–M34 元数据已从本地控制面读取；M35–M37 来自仓库契约。";
      }
    }
  } catch {
    // The repository contract is the deliberate fail-closed fallback.
  }

  return NextResponse.json<CapabilityResponse<MigrationCapability>>({
    source,
    fetchedAt: new Date().toISOString(),
    externalExecutionEvidence: "NOT_RUN",
    capabilities,
    note,
  });
}
