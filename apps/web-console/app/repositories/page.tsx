import type { Metadata } from "next";
import { RepositoryWorkspaceStudio } from "./RepositoryWorkspaceStudio";
import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";

export const metadata: Metadata = { title: "代码仓库工作区" };

export default async function RepositoriesPage() {
  await requirePlatformOperationsSurface("/repositories");
  return <RepositoryWorkspaceStudio />;
}
