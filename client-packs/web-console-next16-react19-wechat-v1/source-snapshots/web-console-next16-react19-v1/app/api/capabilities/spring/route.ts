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
      { id: "spring-framework-xml", label: "Spring Framework XML", detail: "Spring Framework MVC 5.3.39 / Java 11 / Maven 3.9.11 精确夹具已 PASSED_LOCAL；其他经典非 Boot 组合仍需审阅", status: "REVIEW" },
      { id: "spring-framework-annotation", label: "Spring Framework 注解", detail: "精确 MVC 5.3.39 夹具的 @Controller、XML MVC 与 JSP 路线已完成本地工程验证；客户、复杂能力与独立证据仍为 NOT_RUN", status: "REVIEW" },
      { id: "spring-boot-legacy", label: "旧版 Spring Boot", detail: "Boot 1.5.22/Java 8、2.3.12/Java 11、2.7.18/Java 17、3.4.1/Java 17 的精确 Maven 点有 PASSED_LOCAL；Boot 3.5.16/Java 21 与其余精确元组仍为 NOT_RUN，Gradle 为 NOT_IMPLEMENTED，真实执行证据仍为 NOT_RUN", status: "REVIEW" },
    ],
    researchPack: {
      key: "spring-boot-2-7-18-to-3-5-3",
      status: "LIMITED",
      externalEvidence: "NOT_RUN",
    },
    deploymentGuidance: springDeploymentGuidance,
    stages: springModernizationStages,
    note: "Spring Framework MVC 5.3.39 / Java 11 / Maven 3.9.11 → Spring Boot 3.5.3 / Java 21 的精确开发夹具已通过源/目标构建、Tomcat/WarLauncher 启动及 GET/JSP 行为比较，仅属于本地工程证据；Boot 3.5.16 路线和旧 MVC 路线已绑定可执行 Recipe，但精确运行、客户私库、复杂能力、Rootless Runner 和外部独立认证仍为 NOT_RUN，整体仍 NOT_CERTIFIED。",
  });
}
