import type { Metadata } from "next";
import { SmokeConsole } from "./SmokeConsole";

export const metadata: Metadata = { title: "一键冒烟运行" };

export default function SmokePage() {
  return <SmokeConsole />;
}
