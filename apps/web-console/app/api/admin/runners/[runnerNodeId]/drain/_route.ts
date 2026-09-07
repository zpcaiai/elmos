import {
  authorizeAdmin,
  proxyErrorResponse,
  requireAdminMutationSameOrigin,
  requestRunnerDrain,
} from "../../../../../lib/server/operationsProxy";
import {
  relayRunnerFleetMutationResponse,
  validateRunnerFleetMutationRequest,
} from "../../../../../lib/server/runnerFleetPolicy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  context: { params: Promise<{ runnerNodeId: string }> },
) {
  try {
    requireAdminMutationSameOrigin(request);
    const administrator = authorizeAdmin(request, "OPERATOR");
    const { runnerNodeId: rawRunnerNodeId } = await context.params;
    const runnerNodeId = await validateRunnerFleetMutationRequest(
      request,
      rawRunnerNodeId,
      administrator,
      "OPERATOR",
    );
    const upstream = await requestRunnerDrain(runnerNodeId, administrator);
    return relayRunnerFleetMutationResponse(upstream, "DRAINING", runnerNodeId);
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
