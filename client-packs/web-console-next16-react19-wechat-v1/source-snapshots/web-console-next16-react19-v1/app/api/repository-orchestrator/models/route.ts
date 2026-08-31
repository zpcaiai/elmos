import { type NextRequest, NextResponse } from "next/server";

import {
  fetchRepositoryModelCatalog,
  repositoryOrchestratorContext,
  repositoryOrchestratorFailure,
  repositoryOrchestratorPrivateHeaders,
} from "../../../lib/server/repositoryOrchestratorGateway";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  try {
    const context = repositoryOrchestratorContext(request);
    const catalog = await fetchRepositoryModelCatalog(context);
    return NextResponse.json(catalog, { headers: repositoryOrchestratorPrivateHeaders });
  } catch (error) {
    const failure = repositoryOrchestratorFailure(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: repositoryOrchestratorPrivateHeaders,
    });
  }
}
