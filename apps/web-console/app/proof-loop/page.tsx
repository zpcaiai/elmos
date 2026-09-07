import type { Metadata } from "next";

import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";
import { ModernizationProofStudio } from "./ModernizationProofStudio";

export const metadata: Metadata = { title: "现代化证据闭环" };

export const dynamic = "force-dynamic";

export default async function ModernizationProofPage() {
  await requirePlatformOperationsSurface("/proof-loop");
  return <ModernizationProofStudio />;
}
