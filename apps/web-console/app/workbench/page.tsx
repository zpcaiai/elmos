import type { Metadata } from "next";
import { LiveWorkbenchStudio } from "./LiveWorkbenchStudio";

export const metadata: Metadata = { title: "Live Workbench" };

export default function WorkbenchPage() {
  return <LiveWorkbenchStudio />;
}
