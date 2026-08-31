import type { Metadata } from "next";

import { ChinaDbSqlPreflightStudio } from "./ChinaDbSqlPreflightStudio";

export const metadata: Metadata = {
  title: "ChinaDB SQL 只读预检",
};

export default function ChinaDbSqlPreflightPage() {
  return <ChinaDbSqlPreflightStudio />;
}
