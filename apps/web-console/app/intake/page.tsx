import type { Metadata } from "next";
import { MultimodalIntakeWorkbench } from "./MultimodalIntakeWorkbench";
import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";

export const metadata: Metadata = { title: "多模态输入工作台" };

export default async function MultimodalIntakePage() {
  await requirePlatformOperationsSurface("/intake");
  return <MultimodalIntakeWorkbench />;
}

