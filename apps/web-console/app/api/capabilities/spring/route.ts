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
      status: "EXPERIMENTAL",
      externalEvidence: "NOT_RUN",
    },
    deploymentGuidance: springDeploymentGuidance,
    stages: springModernizationStages,
    note: "仓库已能区分经典 Spring Framework 与 Spring Boot；精确实验 Pack 及本地结构 Gate 已通过，但真实客户源/目标运行、holdout 与独立认证仍为 NOT_RUN。",
  });
}
