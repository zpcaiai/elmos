import { NextResponse } from "next/server";
import { springModernizationStages } from "../../../lib/businessLines";
import type { SpringModernizationCapabilityResponse } from "../../../lib/contracts";
import { springDeploymentGuidance } from "../../../lib/deploymentGuidance";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json<SpringModernizationCapabilityResponse>({
    source: "REPOSITORY_CONTRACT",
    fetchedAt: new Date().toISOString(),
    target: { java: "21", framework: "Spring Boot 3.5.3", build: "Maven 3.9.11" },
    recognizedSources: [
      { id: "spring-framework-xml", label: "Spring Framework XML", detail: "可识别 web.xml、DispatcherServlet、applicationContext.xml 与 XML Bean；经典非 Boot 路线未执行，需审阅", status: "REVIEW" },
      { id: "spring-framework-annotation", label: "Spring Framework 注解", detail: "可识别非 Boot 的 @Controller / Java Config；经典非 Boot 路线未执行，需审阅", status: "REVIEW" },
      { id: "spring-boot-legacy", label: "旧版 Spring Boot", detail: "仅 Boot 2.7.18 / Java 17 / Maven 3.9.11 有 PASSED_LOCAL；其余 1.5–3.4 精确元组仍为 NOT_RUN，Gradle 为 NOT_IMPLEMENTED", status: "REVIEW" },
    ],
    researchPack: {
      key: "spring-boot-2-7-18-to-3-5-3",
      status: "LIMITED",
      externalEvidence: "NOT_RUN",
    },
    deploymentGuidance: springDeploymentGuidance,
    stages: springModernizationStages,
    note: "Spring Boot 2.7.18 / Java 17 / Maven 3.9.11 → Spring Boot 3.5.3 / Java 21 的 Web、配置和生命周期子集已通过真实公共仓库、源/目标构建与启动验证，状态为受限支持；DI、校验、持久化仅探测，安全与事务阻断，客户私库、Rootless Runner 和外部独立认证仍为 NOT_RUN。",
  });
}
