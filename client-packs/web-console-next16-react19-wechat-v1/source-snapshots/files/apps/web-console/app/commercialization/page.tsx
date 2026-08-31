import type { Metadata } from "next";
import { CommercializationConsole } from "./CommercializationConsole";

export const metadata: Metadata = { title: "商业化控制面" };

export default function CommercializationPage() {
  return <CommercializationConsole />;
}
