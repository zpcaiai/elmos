import type { Metadata } from "next";
import { MigrationStudio } from "./MigrationStudio";

export const metadata: Metadata = { title: "迁移工坊" };

export default function MigrationPage() {
  return <MigrationStudio />;
}
