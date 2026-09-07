import {
  authorizeAdmin,
  grantPlatformAdmin,
  OperationsProxyError,
  proxyErrorResponse,
  requireAdminMutationSameOrigin,
  revokePlatformAdmin,
} from "../../../lib/server/operationsProxy";
import { readPlatformJson, relayPlatform } from "../platformRelay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    requireAdminMutationSameOrigin(request);
    const body = await readPlatformJson(request);
    const action = body.action;
    if (action !== "GRANT" && action !== "REVOKE") {
      throw new OperationsProxyError(
        400, "PLATFORM_ADMIN_ACTION_INVALID", "操作必须是 GRANT 或 REVOKE。");
    }
    const administrator = authorizeAdmin(request, "APPROVER");
    return relayPlatform(action === "GRANT"
      ? await grantPlatformAdmin(body, administrator)
      : await revokePlatformAdmin(body, administrator));
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
