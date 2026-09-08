import type { Metadata } from "next";
import { AccountOrganizationStudio } from "./AccountOrganizationStudio";
import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";

export const metadata: Metadata = { title: "账户与组织" };

export default async function AccountPage() {
  await requirePlatformOperationsSurface("/account");
  return <AccountOrganizationStudio />;
}
