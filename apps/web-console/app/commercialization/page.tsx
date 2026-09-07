import type { Metadata } from "next";

import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";
import { CommercializationConsole } from "./CommercializationConsole";

export const metadata: Metadata = { title: "商业化控制面" };

export const dynamic = "force-dynamic";

export default async function CommercializationPage() {
  await requirePlatformOperationsSurface("/commercialization");
  return <CommercializationConsole />;
}
