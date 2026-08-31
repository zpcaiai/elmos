import React from "react";
import { PlaygroundWorkspace } from "./PlaygroundWorkspace";

export const metadata = {
  title: "转换与形式化验证准备工作台 | Elmos 工业级软件翻新与迁移工厂",
  description: "准备跨语言转换与形式化验证输入，并明确区分静态示例、未执行状态和真实 Runner 证据。",
};

export default function PlaygroundPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <PlaygroundWorkspace />
    </div>
  );
}
