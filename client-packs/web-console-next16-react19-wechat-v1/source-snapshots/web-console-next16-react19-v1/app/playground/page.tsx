import React from "react";
import { AppShell } from "../components/AppShell";
import { PlaygroundWorkspace } from "./PlaygroundWorkspace";

export const metadata = {
  title: "实时编译与形式化证明沙箱 | Elmos 工业级软件翻新与迁移工厂",
  description: "体验毫秒级 AST 语法降解、双语重构、SMT 形式化不变式证明与 Lean 4 定理综合。",
};

export default function PlaygroundPage() {
  return (
    <AppShell>
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <PlaygroundWorkspace />
      </div>
    </AppShell>
  );
}
