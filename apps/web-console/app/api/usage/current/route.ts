import { NextRequest, NextResponse } from "next/server";
import {
  currentUsageSnapshot,
  UsageMeterError,
} from "../../../lib/server/usageMeter";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vary": "Authorization, X-ELMOS-Tenant, X-ELMOS-Actor",
};

export async function GET(request: NextRequest) {
  try {
    const snapshot = await currentUsageSnapshot(request);
    return NextResponse.json(snapshot, {
      headers: {
        ...privateHeaders,
        "X-ELMOS-Usage-Snapshot-Version": snapshot.snapshotVersion,
      },
    });
  } catch (error) {
    if (error instanceof UsageMeterError) {
      return NextResponse.json(
        {
          code: error.code,
          message: error.message,
          retryable: error.retryable,
          status: error.responseStatus,
        },
        { status: error.httpStatus, headers: privateHeaders },
      );
    }
    return NextResponse.json(
      {
        code: "USAGE_SNAPSHOT_INTERNAL_ERROR",
        message: "实时用量服务发生内部错误。",
        retryable: true,
        status: "ERROR",
      },
      { status: 500, headers: privateHeaders },
    );
  }
}
