import {
  authorizeAdmin,
  cancelOperationsJob,
  proxyErrorResponse,
  requireAdminMutationSameOrigin,
} from "../../../../../lib/server/operationsProxy";
import {
  operationsJobsRequiredRoles,
  relayOperationsJobResponse,
} from "../../../../../lib/server/operationsJobsPolicy";
import { assertEmptyAdminMutationBody } from "../../../../../lib/server/adminMutationPolicy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  context: { params: Promise<{ jobId: string }> },
) {
  try {
    requireAdminMutationSameOrigin(request);
    await assertEmptyAdminMutationBody(request);
    const administrator = authorizeAdmin(request, operationsJobsRequiredRoles.cancel);
    const { jobId } = await context.params;
    const upstream = await cancelOperationsJob(
      jobId,
      new URL(request.url).searchParams,
      administrator,
    );
    return relayOperationsJobResponse(upstream);
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
