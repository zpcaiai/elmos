import { NextResponse } from "next/server";
import { springModernizationStages } from "../../../lib/businessLines";
import type { SpringModernizationCapabilityResponse } from "../../../lib/contracts";
import { springDeploymentGuidance } from "../../../lib/deploymentGuidance";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json<SpringModernizationCapabilityResponse>({
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date().toISOString(),
    target: { java: "21", framework: "Spring Boot 3.5.3", build: "Maven 3.9+ / Gradle exact wrapper" },
    recognizedSources: [
      { id: "spring-framework-xml", label: "Spring Framework XML", detail: "web.xml、DispatcherServlet、applicationContext.xml 与 XML Bean", status: "READY" },
      { id: "spring-framework-annotation", label: "Spring Framework 注解", detail: "非 Boot 的 @Controller / Java Config 应用", status: "READY" },
      { id: "spring-boot-legacy", label: "旧版 Spring Boot", detail: "Boot 1.x/2.x、javax 与旧 Security/JPA 配置", status: "REVIEW" },
    ],
    researchPack: {
      key: "spring-boot-2-7-18-to-3-5-3",
      status: "LIMITED",
      externalEvidence: "NOT_RUN",
    },
    deploymentGuidance: springDeploymentGuidance,
    stages: springModernizationStages,
    note: "Spring Boot 2.7.18→3.5.3 的 Web、配置和生命周期子集已通过真实公共仓库、源/目标构建与启动验证，状态提升为受限支持；客户私库、Rootless Runner 和外部独立认证仍为 NOT_RUN。",
  });
}
