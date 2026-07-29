import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountSessionErrorResponse,
  assertSameOriginMutation,
  oidcConfiguration,
  revokeToken,
  trustedPublicOrigin,
  unsafeCookieValue,
} from "../../../lib/server/accountSession";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    assertSameOriginMutation(request);
  } catch (error) {
    return accountSessionErrorResponse(error);
  }
  const refreshToken = unsafeCookieValue(request, accountCookieNames.refreshToken);
  const accessToken = unsafeCookieValue(request, accountCookieNames.accessToken);
  let revocationConfirmed = false;
  try {
    if (refreshToken || accessToken) {
      revocationConfirmed = await revokeToken(refreshToken || accessToken);
    }
  } catch {
    revocationConfirmed = false;
  }
  let endSessionUrl: string | null = null;
  try {
    const configuration = oidcConfiguration();
    if (configuration.endSessionEndpoint) {
      const target = new URL(configuration.endSessionEndpoint);
      target.searchParams.set(
        "post_logout_redirect_uri",
        new URL("/login", trustedPublicOrigin(request)).toString(),
      );
      endSessionUrl = target.toString();
    }
  } catch {
    endSessionUrl = null;
  }
  const response = NextResponse.json({ loggedOut: true, revocationConfirmed, endSessionUrl });
  for (const name of Object.values(accountCookieNames)) response.cookies.delete(name);
  response.headers.set("Cache-Control", "no-store, private");
  return response;
}
