import { NextResponse, type NextRequest } from "next/server";
import { aggregateGenerationReadiness } from "../../lib/server/generationReadiness";
import { health } from "../../lib/server/generationRunner";
import { probeConfiguredUpstreams } from "../../lib/server/upstreamReadiness";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function deploymentIdentity() {
  const provider = process.env.VERCEL === "1" ? "VERCEL" : "LOCAL";
  const configuredSha = process.env.VERCEL_GIT_COMMIT_SHA?.trim().toLowerCase() ?? "";
  const commitSha = /^[a-f0-9]{40}$/.test(configuredSha) ? configuredSha : null;
  return {
    provider,
    commitSha,
    identityStatus: provider === "VERCEL"
      ? commitSha ? "SHA_BOUND" : "BLOCKED_SHA_NOT_BOUND"
      : "LOCAL_NOT_A_DEPLOYMENT_CLAIM",
  } as const;
}

export async function GET(request: NextRequest) {
  const probe = request.nextUrl.searchParams.get("probe") ?? "readiness";
  if (!["liveness", "readiness"].includes(probe)) {
    return NextResponse.json(
      { status: "BLOCKED", reason: "HEALTH_PROBE_INVALID" },
      { status: 400 },
    );
  }
  if (probe === "liveness") {
    return NextResponse.json(
      { status: "UP", service: "elmos-web-console", checkedAt: new Date().toISOString() },
      { headers: { "Cache-Control": "no-store" } },
    );
  }
  const [runner, dependencies] = await Promise.all([
    health(),
    probeConfiguredUpstreams(),
  ]);
  const generation = aggregateGenerationReadiness({
    localRunner: runner,
    dependencies,
  });
  const deployment = deploymentIdentity();
  const deploymentReady = deployment.provider !== "VERCEL" || deployment.commitSha !== null;
  const ready = generation.status === "READY" && deploymentReady;
  const blocked = generation.status === "BLOCKED" || !deploymentReady;
  const status = ready ? 200 : 503;
  return NextResponse.json(
    {
      status: ready ? "UP" : blocked ? "BLOCKED" : "DEGRADED",
      service: "elmos-web-console",
      localRunner: runner,
      dependencies,
      generation,
      deployment,
      readinessReasons: [
        ...generation.reasons,
        ...(!deploymentReady ? ["VERCEL_DEPLOYMENT_SHA_NOT_BOUND"] : []),
      ],
      checkedAt: new Date().toISOString(),
    },
    { status, headers: { "Cache-Control": "no-store" } },
  );
}
