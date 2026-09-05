import { NextRequest, NextResponse } from "next/server";

import {
  ModernizationProofClientError,
  proofContext,
  subjectDigest,
} from "../../../lib/server/modernizationProofClient";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json({ status: "BLOCKED", reason: "JSON_CONTENT_TYPE_REQUIRED" }, { status: 415 });
    }
    const raw = await request.text();
    if (Buffer.byteLength(raw, "utf-8") > 32 * 1024) {
      return NextResponse.json({ status: "BLOCKED", reason: "REQUEST_TOO_LARGE" }, { status: 413 });
    }
    return NextResponse.json(await subjectDigest(proofContext(request), JSON.parse(raw)));
  } catch (error) {
    const status = error instanceof ModernizationProofClientError ? error.status : 400;
    return NextResponse.json({ status: "BLOCKED", reason: error instanceof Error ? error.message : "SUBJECT_DIGEST_FAILED" }, { status });
  }
}
