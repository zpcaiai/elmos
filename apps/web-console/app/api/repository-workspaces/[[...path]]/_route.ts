import type { NextRequest } from "next/server";
import {
  repositoryWorkspaceError,
  repositoryWorkspaceRequest,
} from "../../../lib/server/repositoryWorkspaceProxy";

type Context = { params: Promise<{ path?: string[] }> };

async function forward(request: NextRequest, context: Context): Promise<Response> {
  try {
    const { path = [] } = await context.params;
    return await repositoryWorkspaceRequest(request, path);
  } catch (error) {
    return repositoryWorkspaceError(error);
  }
}

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
