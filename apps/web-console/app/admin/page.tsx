import type { Metadata } from "next";

import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";
import { OperationsAdmin } from "./OperationsAdmin";

export const metadata: Metadata = {
  title: "运营管理端",
  description: "ELMOS 用户操作、性能与错误观测管理端",
};

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  await requirePlatformOperationsSurface("/admin");
  return <OperationsAdmin />;
}
