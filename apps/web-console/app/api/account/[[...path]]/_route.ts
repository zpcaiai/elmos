import type { NextRequest } from "next/server";
import {
  accountControlPlaneError,
  accountControlPlaneRequest,
} from "../../../lib/server/accountControlPlane";

type Context = { params: Promise<{ path?: string[] }> };

async function forward(request: NextRequest, context: Context): Promise<Response> {
  try {
    const { path = [] } = await context.params;
    return await accountControlPlaneRequest(request, path);
  } catch (error) {
    return accountControlPlaneError(error);
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;
