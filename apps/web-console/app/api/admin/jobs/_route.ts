import {
  authorizeAdmin,
  fetchOperationsJobs,
  proxyErrorResponse,
} from "../../../lib/server/operationsProxy";
import {
  operationsJobsRequiredRoles,
  relayOperationsJobResponse,
} from "../../../lib/server/operationsJobsPolicy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const administrator = authorizeAdmin(request, operationsJobsRequiredRoles.list);
    const upstream = await fetchOperationsJobs(
      new URL(request.url).searchParams,
      administrator,
    );
    return relayOperationsJobResponse(upstream);
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
