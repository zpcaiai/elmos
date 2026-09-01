import type { Metadata } from "next";

import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";
import { SmokeConsole } from "./SmokeConsole";

export const metadata: Metadata = { title: "一键冒烟运行" };

export const dynamic = "force-dynamic";

export default async function SmokePage() {
  await requirePlatformOperationsSurface("/smoke");
  return <SmokeConsole />;
}
