import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";

type InventoryRoute = {
  route_key: string;
  status: "limited" | "research";
  local_execution_status: "PASSED_LOCAL" | "NOT_RUN" | "FAILED";
  repository_execution_status: "PASSED" | "NOT_RUN" | "FAILED";
  independent_verification_status: "PASSED" | "NOT_RUN" | "FAILED";
  external_certification_status: "PASSED" | "NOT_RUN" | "FAILED";
};

type RouteInventory = {
  route_count: number;
  limited_route_count: number;
  research_route_count: number;
  local_execution_evidence: "PASSED" | "NOT_RUN" | "FAILED";
  independent_verification_evidence: "PASSED" | "NOT_RUN" | "FAILED";
  external_certification_evidence: "PASSED" | "NOT_RUN" | "FAILED";
  routes: InventoryRoute[];
};

type ConsoleRoute = {
  id: string;
  status: "LIMITED" | "RESEARCH";
  readiness: "LOCAL_PROFILE_PASSED" | "NOT_RUN";
  localExecution: "PASSED" | "NOT_RUN" | "FAILED";
  repositoryExecutionStatus: "PASSED" | "NOT_RUN" | "FAILED";
  independentVerification: "PASSED" | "NOT_RUN" | "FAILED";
  externalVerification: "PASSED" | "NOT_RUN" | "FAILED";
};

test("Spring 与权威语言路线矩阵保持精确状态并保留未认证边界", async ({
  page,
}) => {
  const inventoryPath = path.resolve(__dirname, "../../..", "routes/inventory.json");
  const inventory = JSON.parse(await readFile(inventoryPath, "utf8")) as RouteInventory;
  expect(inventory.routes).toHaveLength(inventory.route_count);

  const translation = await page.request.get("/api/capabilities/translation");
  expect(translation.status()).toBe(200);
  const translationBody = await translation.json() as {
    routes: ConsoleRoute[];
    routePackageCount: number;
    localExecutionEvidence: string;
    independentVerificationEvidence: string;
    externalExecutionEvidence: string;
    certificationStatus: string;
  };
  expect(translationBody.routePackageCount).toBe(inventory.route_count);
  expect(translationBody.routes).toHaveLength(inventory.route_count);

  const expectedById = new Map(inventory.routes.map((route) => [route.route_key, route]));
  expect(translationBody.routes.map((route) => route.id).sort()).toEqual(
    inventory.routes.map((route) => route.route_key).sort(),
  );
  for (const route of translationBody.routes) {
    const expected = expectedById.get(route.id);
    expect(expected, `inventory route ${route.id}`).toBeDefined();
    expect(route.status).toBe(expected?.status.toUpperCase());
    expect(route.localExecution).toBe(
      expected?.local_execution_status === "PASSED_LOCAL"
        ? "PASSED"
        : expected?.local_execution_status,
    );
    expect(route.readiness).toBe(
      expected?.local_execution_status === "PASSED_LOCAL"
        ? "LOCAL_PROFILE_PASSED"
        : "NOT_RUN",
    );
    expect(route.repositoryExecutionStatus).toBe(expected?.repository_execution_status);
    expect(route.independentVerification).toBe(expected?.independent_verification_status);
    expect(route.externalVerification).toBe(expected?.external_certification_status);
  }
  expect(translationBody.routes.filter((route) => route.status === "LIMITED")).toHaveLength(
    inventory.limited_route_count,
  );
  expect(translationBody.routes.filter((route) => route.status === "RESEARCH")).toHaveLength(
    inventory.research_route_count,
  );
  expect(translationBody.localExecutionEvidence).toBe(inventory.local_execution_evidence);
  expect(translationBody.certificationStatus).toBe("NOT_CERTIFIED");
  expect(translationBody.independentVerificationEvidence).toBe(
    inventory.independent_verification_evidence,
  );
  expect(translationBody.externalExecutionEvidence).toBe(
    inventory.external_certification_evidence,
  );

  const spring = await page.request.get("/api/capabilities/spring");
  expect(spring.status()).toBe(200);
  const springBody = await spring.json();
  expect(springBody.researchPack).toEqual({
    key: "spring-boot-2-7-18-to-3-5-3",
    status: "LIMITED",
    externalEvidence: "NOT_RUN",
  });

  await page.goto("/translation");
  await expect(page.getByText("受限支持", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("未认证", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("本地受限 Profile", { exact: true })).toBeVisible();
});
