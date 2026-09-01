import { NextRequest, NextResponse } from "next/server";

import {
  listProofContracts,
  ModernizationProofClientError,
  proofContext,
} from "../../../lib/server/modernizationProofClient";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    return NextResponse.json(await listProofContracts(proofContext(request)), {
      headers: { "cache-control": "private, no-store" },
    });
  } catch (error) {
    const status = error instanceof ModernizationProofClientError ? error.status : 500;
    return NextResponse.json({ status: "BLOCKED", reason: error instanceof Error ? error.message : "PROOF_CONTRACTS_FAILED" }, { status });
  }
}
