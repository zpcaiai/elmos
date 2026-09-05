import type { NextRequest } from "next/server";
import { dispatchApiRoute } from "../_routeRegistry";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Context = { params: Promise<{ path?: string[] }> };

export function GET(request: NextRequest, context: Context) {
  return dispatchApiRoute(request, context, "GET");
}

export function POST(request: NextRequest, context: Context) {
  return dispatchApiRoute(request, context, "POST");
}

export function PUT(request: NextRequest, context: Context) {
  return dispatchApiRoute(request, context, "PUT");
}

export function PATCH(request: NextRequest, context: Context) {
  return dispatchApiRoute(request, context, "PATCH");
}

export function DELETE(request: NextRequest, context: Context) {
  return dispatchApiRoute(request, context, "DELETE");
}

export function HEAD(request: NextRequest, context: Context) {
  return dispatchApiRoute(request, context, "HEAD");
}

export function OPTIONS(request: NextRequest, context: Context) {
  return dispatchApiRoute(request, context, "OPTIONS");
}
