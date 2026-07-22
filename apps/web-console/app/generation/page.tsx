import type { Metadata } from "next";
import { ProjectGenerationStudio } from "./ProjectGenerationStudio";

export const metadata: Metadata = { title: "多语言项目生成" };

export default function GenerationPage() {
  return <ProjectGenerationStudio />;
}
