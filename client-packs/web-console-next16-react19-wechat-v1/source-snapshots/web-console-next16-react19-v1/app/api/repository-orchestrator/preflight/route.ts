import { type NextRequest, NextResponse } from "next/server";

import {
  parseRepositoryPreflightRequest,
  RepositoryOrchestratorContractError,
  repositoryOrchestratorRequestLimitBytes,
} from "../../../lib/repositoryOrchestratorContracts";
import { BoundedJsonError, readBoundedJson } from "../../../lib/server/boundedJson";
import {
  repositoryOrchestratorContext,
  repositoryOrchestratorFailure,
  repositoryOrchestratorPrivateHeaders,
  submitRepositoryPreflight,
} from "../../../lib/server/repositoryOrchestratorGateway";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    const context = repositoryOrchestratorContext(request);
    const raw = await readBoundedJson(
      request,
      repositoryOrchestratorRequestLimitBytes,
      "REPOSITORY_PREFLIGHT_REQUEST_TOO_LARGE",
    );
    const preflight = parseRepositoryPreflightRequest(raw);
    const upstream = await submitRepositoryPreflight(context, preflight);
    return NextResponse.json(upstream.result, {
      status: upstream.status,
      headers: repositoryOrchestratorPrivateHeaders,
    });
  } catch (error) {
    const normalized = error instanceof BoundedJsonError
      ? new RepositoryOrchestratorContractError(error.status, error.message)
      : error;
    const failure = repositoryOrchestratorFailure(normalized);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: repositoryOrchestratorPrivateHeaders,
    });
  }
}
