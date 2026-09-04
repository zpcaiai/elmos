import {
  adjustPlatformWallet,
  authorizeAdmin,
  proxyErrorResponse,
  requireAdminMutationSameOrigin,
} from "../../../../lib/server/operationsProxy";
import { readPlatformJson, relayPlatform } from "../../platformRelay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    requireAdminMutationSameOrigin(request);
    const body = await readPlatformJson(request);
    // APPROVER：手工改余额是这个子系统里最危险的动作，
    // 也是唯一一个在别处没有对照记录的动作——没有支付、没有任务，
    // 能对账的只有管理员打进去的那句原因。
    const administrator = authorizeAdmin(request, "APPROVER");
    return relayPlatform(await adjustPlatformWallet(body, administrator));
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
