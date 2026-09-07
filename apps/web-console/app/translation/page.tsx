import type { Metadata } from "next";
import { TranslationStudio } from "./TranslationStudio";

export const metadata: Metadata = { title: "全库跨语言转换" };

export default function TranslationPage() {
  return <TranslationStudio />;
}
