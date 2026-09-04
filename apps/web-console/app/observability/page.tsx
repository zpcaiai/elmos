import type { Metadata } from "next";

import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";
import { ObservabilityWorkspace } from "./ObservabilityWorkspace";

export const metadata: Metadata = {
  title: "全链路观测与存证",
  description: "管理员端：OTLP 链路、SLSA 存证与运行时观测",
};

export const dynamic = "force-dynamic";

export default async function ObservabilityPage() {
  await requirePlatformOperationsSurface("/observability");
  return <ObservabilityWorkspace />;
}
