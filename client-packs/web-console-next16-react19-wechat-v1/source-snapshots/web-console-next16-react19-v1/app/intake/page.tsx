import type { Metadata } from "next";
import { MultimodalIntakeWorkbench } from "./MultimodalIntakeWorkbench";

export const metadata: Metadata = { title: "多模态输入工作台" };

export default function MultimodalIntakePage() {
  return <MultimodalIntakeWorkbench />;
}
