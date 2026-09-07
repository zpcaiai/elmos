import {
  authorizeAdmin,
  fetchPlatformLedger,
  proxyErrorResponse,
} from "../../../../../lib/server/operationsProxy";
import { relayPlatform } from "../../../platformRelay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ organizationId: string }> },
) {
  try {
    const administrator = authorizeAdmin(request, "VIEWER");
    const { organizationId } = await context.params;
    return relayPlatform(await fetchPlatformLedger(
      organizationId, new URL(request.url).searchParams, administrator));
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
