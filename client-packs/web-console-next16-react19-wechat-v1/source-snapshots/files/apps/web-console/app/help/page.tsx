import type { Metadata } from "next";
import { HelpCenter } from "./HelpCenter";

export const metadata: Metadata = {
  title: "帮助与就绪状态",
  description: "ELMOS 三条业务线、仓库交付、管理端和外部验证边界",
};

export default function HelpPage() {
  return <HelpCenter />;
}
