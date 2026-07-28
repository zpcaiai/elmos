import { NextResponse } from "next/server";
import type { TranslationCapabilityBlocked } from "../../../lib/contracts";
import { TranslationContractError, readTranslationCapability } from "../../../lib/server/translationRoutes";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(readTranslationCapability(), {
      headers: { "cache-control": "no-store" },
    });
  } catch (error) {
    const blocked: TranslationCapabilityBlocked = {
      source: "REPOSITORY_CONTRACT",
      fetchedAt: new Date().toISOString(),
      status: "BLOCKED",
      errorCode: error instanceof TranslationContractError
        ? error.errorCode
        : "TRANSLATION_CONTRACT_UNAVAILABLE",
      message: error instanceof TranslationContractError
        ? error.message
        : "跨语言路线能力契约不可读取。",
    };
    return NextResponse.json(blocked, { status: 503, headers: { "cache-control": "no-store" } });
  }
}
