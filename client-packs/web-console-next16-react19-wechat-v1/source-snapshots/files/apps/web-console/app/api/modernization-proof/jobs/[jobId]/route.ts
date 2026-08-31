import { NextRequest, NextResponse } from "next/server";

import {
  cancelProofJob,
  getProofJob,
  ModernizationProofClientError,
  proofContext,
} from "../../../../lib/server/modernizationProofClient";

export const dynamic = "force-dynamic";

function blocked(error: unknown) {
  const status = error instanceof ModernizationProofClientError ? error.status : 500;
  return NextResponse.json({ status: "BLOCKED", reason: error instanceof Error ? error.message : "PROOF_JOB_FAILED" }, { status });
}

export async function GET(request: NextRequest, context: { params: Promise<{ jobId: string }> }) {
  try {
    const { jobId } = await context.params;
    return NextResponse.json(await getProofJob(proofContext(request), jobId), {
      headers: { "cache-control": "private, no-store" },
    });
  } catch (error) { return blocked(error); }
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ jobId: string }> }) {
  try {
    const { jobId } = await context.params;
    return NextResponse.json(await cancelProofJob(proofContext(request), jobId), { status: 202 });
  } catch (error) { return blocked(error); }
}
