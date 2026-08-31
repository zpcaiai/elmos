import {
  authorizeAdmin,
  fetchPlatformWallets,
  proxyErrorResponse,
} from "../../../lib/server/operationsProxy";
import { relayPlatform } from "../platformRelay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    // VIEWER 是本地会话层的门槛；跨组织的那道门在控制面与数据库里，
    // 这里过了不代表那里会过。
    const administrator = authorizeAdmin(request, "VIEWER");
    return relayPlatform(
      await fetchPlatformWallets(new URL(request.url).searchParams, administrator));
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
