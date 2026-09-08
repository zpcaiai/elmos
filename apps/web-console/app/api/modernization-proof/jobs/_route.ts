import { NextRequest, NextResponse } from "next/server";

import {
  createProofJob,
  type ModernizationProofSubmission,
  ModernizationProofClientError,
  proofContext,
} from "../../../lib/server/modernizationProofClient";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json({ status: "BLOCKED", reason: "JSON_CONTENT_TYPE_REQUIRED" }, { status: 415 });
    }
    const raw = await request.text();
    if (Buffer.byteLength(raw, "utf-8") > 256 * 1024) {
      return NextResponse.json({ status: "BLOCKED", reason: "REQUEST_TOO_LARGE" }, { status: 413 });
    }
    const body = JSON.parse(raw) as ModernizationProofSubmission;
    return NextResponse.json(await createProofJob(proofContext(request), body), { status: 202 });
  } catch (error) {
    const status = error instanceof ModernizationProofClientError ? error.status : 400;
    return NextResponse.json({ status: "BLOCKED", reason: error instanceof Error ? error.message : "PROOF_JOB_CREATE_FAILED" }, { status });
  }
}
