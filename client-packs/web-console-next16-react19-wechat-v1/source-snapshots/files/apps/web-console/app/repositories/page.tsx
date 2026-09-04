import type { Metadata } from "next";
import { RepositoryWorkspaceStudio } from "./RepositoryWorkspaceStudio";

export const metadata: Metadata = { title: "代码仓库工作区" };

export default function RepositoriesPage() {
  return <RepositoryWorkspaceStudio />;
}
