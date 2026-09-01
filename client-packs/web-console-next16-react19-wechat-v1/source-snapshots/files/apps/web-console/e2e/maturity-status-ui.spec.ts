import { expect, test } from "@playwright/test";

test("Spring 与 30 条语言路线只提升为受限支持并保留未认证边界", async ({
  page,
}) => {
  const translation = await page.request.get("/api/capabilities/translation");
  expect(translation.status()).toBe(200);
  const translationBody = await translation.json();
  expect(translationBody.routes).toHaveLength(30);
  expect(
    translationBody.routes.every(
      (route: { status: string }) => route.status === "LIMITED",
    ),
  ).toBe(true);
  expect(translationBody.certificationStatus).toBe("NOT_CERTIFIED");
  expect(translationBody.independentVerificationEvidence).toBe("NOT_RUN");
  expect(translationBody.externalExecutionEvidence).toBe("NOT_RUN");

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
