import type { Metadata } from "next";
import { SkillsWorkspace } from "./SkillsWorkspace";

export const metadata: Metadata = { title: "Skills 与验证" };

export default function SkillsPage() {
  return <SkillsWorkspace />;
}
