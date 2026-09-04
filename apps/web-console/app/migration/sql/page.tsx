import type { Metadata } from "next";

import { ChinaDbSqlPreflightStudio } from "./ChinaDbSqlPreflightStudio";

export const metadata: Metadata = {
  title: "ChinaDB SQL 预检",
};

export default function ChinaDbSqlPreflightPage() {
  return <ChinaDbSqlPreflightStudio />;
}
