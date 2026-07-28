import { NextRequest, NextResponse } from "next/server";
import {
  currentUsageSnapshot,
  UsageMeterError,
} from "../../../lib/server/usageMeter";
import {
  commercialBillingRequest,
  proxyError,
} from "../../../lib/server/commercialBillingProxy";
import { createHash } from "node:crypto";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vary": "Cookie, Authorization",
};

export async function GET(request: NextRequest) {
  if (process.env.ELMOS_LOCAL_RUNNER_ENABLED !== "true") {
    try {
      const response = await commercialBillingRequest(
        request,
        "/commercial/v1/billing/usage/current",
      );
      const text = await response.text();
      if (!response.ok) {
        return new NextResponse(text, {
          status: response.status,
          headers: { ...privateHeaders, "Content-Type": "application/json" },
        });
      }
      const source = JSON.parse(text) as Record<string, unknown>;
      const snapshotVersion = createHash("sha256").update(text).digest("hex");
      const normalizeMeasure = (value: unknown) => {
        const measure = value as Record<string, unknown>;
        return {
          consumed: measure.consumed,
          reserved: measure.reserved,
          limit: measure.limit,
          remaining: measure.remaining,
          usageBps: measure.usageBps,
          hardStop: measure.hardStop,
        };
      };
      return NextResponse.json({
        schemaVersion: "1.0.0",
        snapshotVersion,
        status: source.status,
        subject: {
          tenantId: source.organizationId,
          actorId: source.actorId,
        },
        plan: {
          planId: source.planId,
          displayName: source.displayName,
          allowanceWindow: source.allowanceWindow,
        },
        period: {
          startsAt: source.periodStartsAt,
          endsAt: source.periodEndsAt,
          resetsAt: source.resetsAt,
        },
        tokens: normalizeMeasure(source.tokens),
        credits: normalizeMeasure(source.credits),
        reconciledEventCount: source.reconciledEventCount,
        unreconciledEventCount: source.unreconciledEventCount,
        duplicateEventCount: 0,
        eventWatermark: source.eventWatermark,
        generatedAt: source.generatedAt,
        refreshAfterSeconds: source.refreshAfterSeconds,
      }, {
        headers: {
          ...privateHeaders,
          "X-ELMOS-Usage-Snapshot-Version": snapshotVersion,
        },
      });
    } catch (error) {
      const mapped = proxyError(error);
      return NextResponse.json(mapped.body, {
        status: mapped.status,
        headers: privateHeaders,
      });
    }
  }
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
