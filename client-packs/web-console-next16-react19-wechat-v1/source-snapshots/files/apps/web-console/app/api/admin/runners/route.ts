import {
  authorizeAdmin,
  fetchOperationsRunnerFleet,
  proxyErrorResponse,
} from "../../../lib/server/operationsProxy";
import {
  relayRunnerFleetResponse,
  runnerFleetRequiredRole,
} from "../../../lib/server/runnerFleetPolicy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const administrator = authorizeAdmin(request, runnerFleetRequiredRole);
    const upstream = await fetchOperationsRunnerFleet(
      new URL(request.url).searchParams,
      administrator,
    );
    return relayRunnerFleetResponse(upstream);
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
