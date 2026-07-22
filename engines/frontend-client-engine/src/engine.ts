import { createHash } from "node:crypto";
import { buildUiSemanticGraph, discoverWorkspace } from "./analyzer.js";
import type { Capabilities, EngineJobRequest, ExecuteStepRequest, FrontendErrorCode, JobResponse } from "./contracts.js";
import type { TargetProfile, WorkspaceInventory } from "./domain.js";
import { planFrontendMigration } from "./planner.js";

function requireText(value: string, name: string): void {
  if (!value?.trim()) throw new Error(`${name} is required`);
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function fingerprint(operation: string, request: EngineJobRequest | ExecuteStepRequest): string {
  return createHash("sha256").update(canonical({ operation, request })).digest("hex");
}

function problem(jobId: string, code: FrontendErrorCode, message: string, retryable = false): JobResponse {
  return { schemaVersion: "1.0", jobId, status: "FAILED", evidenceRefs: [],
    result: { configured: false, executed: false, customerCodeExecuted: false },
    error: { errorCode: code, message, retryable } };
}

function asFiles(input: Readonly<Record<string, unknown>> | undefined): Readonly<Record<string, string>> {
  const files = input?.files;
  if (!files || typeof files !== "object" || Array.isArray(files)) throw new Error("FRONTEND_WORKSPACE_NOT_FOUND");
  const result: Record<string, string> = {};
  for (const [path, content] of Object.entries(files as Record<string, unknown>)) {
    if (typeof content !== "string") throw new Error(`source content must be text: ${path}`);
    result[path] = content;
  }
  return result;
}

export class FrontendClientEngine {
  private readonly jobs = new Map<string, JobResponse>();
  private readonly idempotency = new Map<string, { fingerprint: string; response: JobResponse }>();

  capabilities(): Capabilities {
    return {
      schemaVersion: "1.0", engine: "ELMOS_FRONTEND_CLIENT", engineVersion: "1.0.0",
      languages: ["JAVASCRIPT", "TYPESCRIPT", "HTML", "CSS"],
      webFrameworks: ["ANGULARJS", "ANGULAR", "VUE2", "VUE3", "REACT", "JQUERY"],
      desktopFrameworks: ["ELECTRON", "WPF", "WINFORMS", "WEBVIEW", "JAVA_DESKTOP_INVENTORY", "QT_INVENTORY"],
      mobileFrameworks: ["ANDROID_VIEWS", "ANDROID_COMPOSE", "UIKIT", "SWIFTUI", "REACT_NATIVE", "FLUTTER", "CORDOVA", "IONIC"],
      runnerProfiles: { WEB_LEGACY: "NOT_CONFIGURED", MODERN_WEB: "NOT_CONFIGURED", BROWSER_MATRIX: "NOT_CONFIGURED", DESKTOP_WINDOWS: "NOT_CONFIGURED", DESKTOP_MACOS: "NOT_CONFIGURED", ANDROID: "NOT_CONFIGURED", IOS: "NOT_CONFIGURED" },
      staticAnalysis: "READY", customerCodeExecution: "RUNNER_REQUIRED_FAIL_CLOSED"
    };
  }

  scan(request: EngineJobRequest): JobResponse {
    return this.once("scan", request, jobId => {
      try {
        const files = asFiles(request.input);
        const inventory = discoverWorkspace(request.snapshotId, files);
        const graph = buildUiSemanticGraph(request.workspaceRef, files);
        const hash = createHash("sha256").update(canonical({ inventory, graph })).digest("hex");
        return { schemaVersion: "1.0", jobId, status: "SUCCEEDED", evidenceRefs: [`artifact://frontend/${hash}`],
          result: { configured: true, executed: true, customerCodeExecuted: false, inventory, graph } };
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return problem(jobId, message === "FRONTEND_WORKSPACE_NOT_FOUND" ? "FRONTEND_WORKSPACE_NOT_FOUND" : "FRONTEND_ROUTE_DISCOVERY_FAILED", message);
      }
    });
  }

  plan(request: EngineJobRequest): JobResponse {
    return this.once("plan", request, jobId => {
      try {
        const inventory = request.input?.inventory as WorkspaceInventory | undefined;
        const target = request.input?.target as TargetProfile | undefined;
        if (!inventory || !target) throw new Error("scan inventory and target profile are required");
        const versions = (request.input?.currentVersions ?? {}) as Readonly<Record<string, string>>;
        const plan = planFrontendMigration(inventory, target, versions);
        const hash = createHash("sha256").update(canonical(plan)).digest("hex");
        return { schemaVersion: "1.0", jobId, status: plan.blockers.length ? "FAILED" : "SUCCEEDED",
          evidenceRefs: [`artifact://frontend-plan/${hash}`], result: { configured: true, executed: true, customerCodeExecuted: false, plan },
          ...(plan.blockers.length ? { error: { errorCode: "FRONTEND_PLAN_BLOCKED" as const, message: plan.blockers.join(","), retryable: false } } : {}) };
      } catch (error) {
        return problem(jobId, "FRONTEND_ROUTE_DISCOVERY_FAILED", error instanceof Error ? error.message : String(error));
      }
    });
  }

  executeStep(request: ExecuteStepRequest): JobResponse {
    return this.once("execute-step", request, jobId => problem(jobId, "RUNNER_NOT_CONFIGURED",
      `approved ${request.runnerProfile} Runner is required for step ${request.stepId}`));
  }

  validate(request: EngineJobRequest): JobResponse {
    return this.once("validate", request, jobId => {
      const baseline = request.input?.baselineEvidenceRefs;
      const target = request.input?.targetEvidenceRefs;
      const manual = request.input?.manualEvidenceRefs;
      const requiresManual = request.input?.requiresManual !== false;
      if (!Array.isArray(baseline) || baseline.length === 0 || !Array.isArray(target) || target.length === 0
          || (requiresManual && (!Array.isArray(manual) || manual.length === 0))) {
        return problem(jobId, "ACCESSIBILITY_PROFILE_MISSING", "baseline, target and required manual evidence must be present");
      }
      const refs = [...baseline, ...target, ...(Array.isArray(manual) ? manual : [])].filter((value): value is string => typeof value === "string" && value.length > 0);
      if (refs.length === 0) return problem(jobId, "ACCESSIBILITY_PROFILE_MISSING", "validation evidence is empty");
      return { schemaVersion: "1.0", jobId, status: "SUCCEEDED", evidenceRefs: [...new Set(refs)].sort(),
        result: { configured: true, executed: true, customerCodeExecuted: false,
          validationOutcome: "EVIDENCE_ACCEPTED_FOR_INDEPENDENT_JUDGMENT", independentValidationRequired: true } };
    });
  }

  job(organizationId: string, jobId: string): JobResponse {
    requireText(organizationId, "organizationId"); requireText(jobId, "jobId");
    const response = this.jobs.get(`${organizationId}:${jobId}`);
    return response ?? problem(jobId, "JOB_NOT_FOUND", "job is not visible to this organization");
  }

  cancel(organizationId: string, jobId: string): JobResponse {
    const response = this.job(organizationId, jobId);
    if (response.error?.errorCode === "JOB_NOT_FOUND") return response;
    if (["SUCCEEDED", "FAILED", "CANCELLED"].includes(response.status)) return problem(jobId, "JOB_TERMINAL", "terminal job cannot be cancelled");
    const cancelled: JobResponse = { ...response, status: "CANCELLED" };
    this.jobs.set(`${organizationId}:${jobId}`, cancelled);
    return cancelled;
  }

  private once(operation: string, request: EngineJobRequest | ExecuteStepRequest, action: (jobId: string) => JobResponse): JobResponse {
    requireText(request.organizationId, "organizationId"); requireText(request.snapshotId, "snapshotId");
    requireText(request.idempotencyKey, "idempotencyKey"); requireText(request.workspaceRef, "workspaceRef");
    const key = `${request.organizationId}:${operation}:${request.idempotencyKey}`;
    const currentFingerprint = fingerprint(operation, request);
    const previous = this.idempotency.get(key);
    if (previous) {
      if (previous.fingerprint !== currentFingerprint) return problem(previous.response.jobId, "IDEMPOTENCY_CONFLICT", "idempotency key reused with different input");
      return previous.response;
    }
    const jobId = createHash("sha256").update(key).digest("hex").slice(0, 24);
    const response = action(jobId);
    this.idempotency.set(key, { fingerprint: currentFingerprint, response });
    this.jobs.set(`${request.organizationId}:${jobId}`, response);
    return response;
  }
}
