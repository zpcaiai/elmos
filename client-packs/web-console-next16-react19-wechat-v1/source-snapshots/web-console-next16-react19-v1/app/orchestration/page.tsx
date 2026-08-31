import type { Metadata } from "next";

import { RepositoryOrchestratorWorkbench } from "./RepositoryOrchestratorWorkbench";

export const metadata: Metadata = {
  title: "仓库任务编排预检",
  description: "仓库任务分解、模型路由、成本与证据就绪度的只读预检。",
};

export default function RepositoryOrchestrationPage() {
  return <RepositoryOrchestratorWorkbench />;
}
