import type { Metadata } from "next";
import { AccountOrganizationStudio } from "./AccountOrganizationStudio";

export const metadata: Metadata = { title: "账户与组织" };

export default function AccountPage() {
  return <AccountOrganizationStudio />;
}
