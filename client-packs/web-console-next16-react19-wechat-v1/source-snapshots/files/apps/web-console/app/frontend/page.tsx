import type { Metadata } from "next";

import { FrontendTransformationStudio } from "./FrontendTransformationStudio";

export const metadata: Metadata = {
  title: "前端转换工厂",
  description: "FRT G01–G30 前端仓库发现、语义转换、路线规划与证据治理工作台",
};

export default function FrontendTransformationPage() {
  return <FrontendTransformationStudio />;
}
