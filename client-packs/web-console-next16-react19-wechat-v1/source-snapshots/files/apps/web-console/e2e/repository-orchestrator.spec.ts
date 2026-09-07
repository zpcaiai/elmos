import { expect, test } from "@playwright/test";

const modelSeeds = [
  ["gpt-5.6-sol-max", "GPT-5.6 Sol Max", "openai", "architect_verifier", 5, ["L2", "L3", "L4"]],
  ["claude-opus-5-max", "Claude Opus 5 Max", "anthropic", "architect_repo_expert", 5, ["L3", "L4"]],
  ["claude-fable-5", "Claude Fable 5", "anthropic", "long_horizon_migration", 5, ["L4"]],
  ["grok-4.6", "Grok 4.6", "xai", "terminal_general_worker", 3, ["L1", "L2"]],
  ["kimi-k3-max", "Kimi K3 Max", "moonshot", "long_context_worker", 2, ["L1", "L2"]],
  ["glm-5.3-max", "GLM-5.3 Max", "zhipu", "cost_efficient_worker", 1, ["L0"]],
  ["qwen3.8-max", "Qwen3.8-Max", "alibaba", "cost_efficient_worker", 1, ["L0"]],
  ["deepseek-v4-pro-0813", "DeepSeek V4 Pro 0813", "deepseek", "backend_algorithm_worker", 1, ["L1"]],
  ["gemini-3.7-flash-high", "Gemini 3.7 Flash High", "google", "fast_worker", 1, ["L0"]],
  ["claude-sonnet-5", "Claude Sonnet 5", "anthropic", "balanced_worker_reviewer", 3, ["L1", "L2"]],
] as const;

const evidence = {
  providerInvocation: "NOT_RUN",
  taskDecomposition: "NOT_RUN",
  runCreation: "NOT_RUN",
  workspaceMutation: "NOT_RUN",
  scmEffects: "NOT_RUN",
  externalVerification: "NOT_RUN",
  certification: "NOT_CERTIFIED",
} as const;

const catalog = {
  schemaVersion: "1.0",
  catalogVersion: "repository-model-catalog-v1.1.0",
  selectionVersion: "repository-model-selection-v1",
  selectionModes: ["smart", "manual"],
  defaultMode: "smart",
  optimizationProfiles: ["cost_performance", "lowest_cost", "max_quality", "fastest"],
  fallbackPolicies: ["strict", "smart_within_allowlist"],
  verificationPolicies: ["system_required_verifiers", "selected_model_only"],
  models: modelSeeds.map(([alias, displayName, provider, roleHint, relativeCostTier, routingTiers]) => ({
    alias,
    displayName,
    provider,
    roleHint,
    relativeCostTier,
    routingTiers,
    highestRoutingTier: routingTiers.at(-1),
    providerModelId: null,
    pricing: {
      inputPerMillion: null,
      cachedInputPerMillion: null,
      outputPerMillion: null,
      currency: "USD",
      source: "operator_or_live_adapter",
      effectiveAt: null,
    },
    limits: { contextTokens: null, maxOutputTokens: null, concurrency: null },
    capabilities: [],
    deploymentId: null,
    exactModelRevision: null,
    providerGatewayAdapterId: null,
    observedAt: null,
    profileMaxAgeSeconds: null,
    quotaRemainingTokens: null,
    activeConcurrency: null,
    residencies: [],
    privacyPolicyId: null,
    supportsPrivateRepositories: null,
    status: "NOT_CONFIGURED",
    available: false,
    selectable: false,
    reasons: ["PROVIDER_MODEL_ID_UNSET", "INPUT_PRICE_UNSET", "CAPABILITIES_UNSET"],
  })),
  status: "NOT_CONFIGURED",
  reasons: [
    "OPERATOR_RUNTIME_PROFILE_REQUIRED",
    "PROVIDER_IDS_PRICES_LIMITS_AND_CAPABILITIES_MUST_BE_TRUSTED_SERVER_CONFIG",
    "CONFIGURED_MODELS=0/10",
  ],
  runtimeProfilesAcceptedFromClient: false,
  evidence,
};

test("Smart-first repository preflight consumes the server catalog and stays fail-closed", async ({ page }) => {
  let submitted: Record<string, unknown> | null = null;
  const sideEffectRequests: string[] = [];

  page.on("request", (request) => {
    if (/\/(?:runs?|providers?|scm|workspaces?|commits?|push)(?:\/|\?|$)/i.test(new URL(request.url()).pathname)) {
      sideEffectRequests.push(request.url());
    }
  });
  await page.route("**/api/telemetry/events", (route) => route.fulfill({ status: 204, body: "" }));
  await page.route("**/api/auth/session", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ authenticated: false }),
  }));
  await page.route("**/api/repository-orchestrator/models", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    headers: { "Cache-Control": "private, no-store" },
    body: JSON.stringify(catalog),
  }));
  await page.route("**/api/repository-orchestrator/preflight", async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    const selection = submitted;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "Cache-Control": "private, no-store" },
      body: JSON.stringify({
        schemaVersion: "1.0",
        catalogVersion: catalog.catalogVersion,
        status: "BLOCKED",
        validationStatus: "VALID",
        configurationStatus: "NOT_CONFIGURED",
        reasons: ["NO_CONFIGURED_MODEL_MEETS_RISK_FLOOR:L0"],
        selection: {
          schemaVersion: selection.schemaVersion,
          catalogVersion: selection.catalogVersion,
          selectionVersion: selection.selectionVersion,
          mode: selection.mode,
          selectedModel: selection.selectedModel,
          optimizationProfile: selection.optimizationProfile,
          fallbackPolicy: selection.mode === "smart" ? "router_policy" : selection.fallbackPolicy,
          verificationPolicy: selection.verificationPolicy,
          selectionSource: "api",
          lockedByUser: selection.mode === "manual",
          immutable: true,
          digest: "a".repeat(64),
        },
        risk: selection.risk,
        minimumRoutingTier: "L0",
        resolvedModel: null,
        dag: {
          status: "NOT_RUN",
          requiredStages: [
            "requirement_normalization",
            "repository_intake",
            "atomic_task_decomposition",
            "task_dag_build",
            "cost_performance_routing",
            "deterministic_validation",
          ],
          tasks: [],
          waves: [],
          criticalPath: [],
          reason: "Preflight validates selection and routing readiness only; no repository task DAG was created.",
        },
        cost: {
          status: "NOT_CONFIGURED",
          currency: "USD",
          estimatedRunCost: null,
          formula: "invoke_cost + escalation_cost + integration_risk_cost + retry_penalty",
          reason: "Exact cost is unavailable until trusted provider prices and limits are configured.",
        },
        auditExplanation: [
          "Selection is immutable for this preflight.",
          "Provider invocation, task decomposition, run creation, workspace mutation, and SCM effects are NOT_RUN.",
        ],
        runtimeProfilesAcceptedFromClient: false,
        evidence,
      }),
    });
  });

  await page.goto("/orchestration");

  await expect(page.getByRole("heading", { name: "仓库任务编排预检" })).toBeVisible();
  const smartMode = page.getByRole("radio", { name: /Smart — 每个任务的最佳价值/ });
  const manualMode = page.getByRole("radio", { name: /手动选择主实现模型/ });
  await expect(smartMode).toBeChecked();
  await expect(smartMode).toBeInViewport();

  const modelRadios = page.locator('input[name="manual-model"]');
  await expect(modelRadios).toHaveCount(10);
  for (let index = 0; index < modelSeeds.length; index += 1) {
    await expect(modelRadios.nth(index)).toBeDisabled();
    await expect(page.getByText(modelSeeds[index][0], { exact: true })).toBeVisible();
  }

  await manualMode.check();
  const fallback = page.getByRole("checkbox", { name: /allowlist 内智能 fallback/ });
  await fallback.check();
  await expect(fallback).toBeChecked();
  await expect(page.getByRole("button", { name: "运行保守预检" })).toBeDisabled();

  await smartMode.check();
  await page.getByRole("button", { name: "运行保守预检" }).click();
  await expect.poll(() => submitted).not.toBeNull();
  expect(submitted).toMatchObject({
    mode: "smart",
    selectedModel: null,
    fallbackPolicy: null,
  });
  expect(submitted).not.toHaveProperty("runtimeProfiles");
  expect(submitted).not.toHaveProperty("selectionSource");
  expect(submitted).not.toHaveProperty("lockedByUser");
  expect(submitted).not.toHaveProperty("resolvedModel");

  await expect(page.getByRole("heading", { name: "预检结果" })).toBeVisible();
  await expect(page.getByText("BLOCKED", { exact: true })).toBeVisible();
  await expect(page.getByText("NOT_RUN", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("NOT_CERTIFIED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("NO CONFIGURED MODEL MEETS RISK FLOOR · L0", { exact: true })).toBeVisible();
  expect(sideEffectRequests).toEqual([]);
});
