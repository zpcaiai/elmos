import {
  authorizeAdmin,
  fetchPlatformJobs,
  proxyErrorResponse,
} from "../../../lib/server/operationsProxy";
import { relayPlatform } from "../platformRelay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * 跨组织任务视图。
 *
 * 与既有的 /api/admin/jobs 并存而不是取代它：那条走
 * operations-observability，每个端点都强制带组织头并对该组织授权，
 * 是组织内视图。两者的授权模型不同，合成一个端点会让「我在看谁的数据」
 * 取决于有没有传某个参数。
 */
export async function GET(request: Request) {
  try {
    const administrator = authorizeAdmin(request, "VIEWER");
    return relayPlatform(
      await fetchPlatformJobs(new URL(request.url).searchParams, administrator));
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
