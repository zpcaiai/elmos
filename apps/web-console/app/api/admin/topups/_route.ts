import {
  authorizeAdmin,
  fetchPlatformTopups,
  proxyErrorResponse,
} from "../../../lib/server/operationsProxy";
import { relayPlatform } from "../platformRelay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const administrator = authorizeAdmin(request, "VIEWER");
    return relayPlatform(
      await fetchPlatformTopups(new URL(request.url).searchParams, administrator));
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
