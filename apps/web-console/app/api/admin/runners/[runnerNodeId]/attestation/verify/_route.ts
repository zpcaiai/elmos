import {
  authorizeAdmin,
  proxyErrorResponse,
  requireAdminMutationSameOrigin,
  verifyRunnerAttestation,
} from "../../../../../../lib/server/operationsProxy";
import {
  relayRunnerFleetMutationResponse,
  validateRunnerFleetMutationRequest,
} from "../../../../../../lib/server/runnerFleetPolicy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  context: { params: Promise<{ runnerNodeId: string }> },
) {
  try {
    requireAdminMutationSameOrigin(request);
    const administrator = authorizeAdmin(request, "APPROVER");
    const { runnerNodeId: rawRunnerNodeId } = await context.params;
    const runnerNodeId = await validateRunnerFleetMutationRequest(
      request,
      rawRunnerNodeId,
      administrator,
      "APPROVER",
    );
    const upstream = await verifyRunnerAttestation(runnerNodeId, administrator);
    return relayRunnerFleetMutationResponse(upstream, "READY", runnerNodeId);
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
