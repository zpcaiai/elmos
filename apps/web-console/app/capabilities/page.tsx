import type { Metadata } from "next";
import { CapabilityCenter } from "./CapabilityCenter";
import { requirePlatformOperationsSurface } from "../lib/server/surfaceGuards";

export const metadata: Metadata = {
  title: "功能能力中心",
  description: "ELMOS 平台已实现的功能，按业务域列出实现范围与验证状态",
};

export default async function CapabilitiesPage() {
  await requirePlatformOperationsSurface("/capabilities");
  return <CapabilityCenter />;
}
