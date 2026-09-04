import type { Metadata } from "next";

import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";
import { GovernanceWorkspace } from "./GovernanceWorkspace";

export const metadata: Metadata = {
  title: "契约治理与变异",
  description: "管理员端：API 契约差异与变异测试治理",
};

export const dynamic = "force-dynamic";

export default async function GovernancePage() {
  await requirePlatformOperationsSurface("/governance");
  return <GovernanceWorkspace />;
}
