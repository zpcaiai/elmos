import type { MiniappGeneratedProject } from "./miniapp-target-generation.js";
import { miniappIrDigest } from "./miniapp-semantic-ir.js";
import type { MiniappConversionRequest, MiniappPlatform } from "./miniapp-types.js";

export const MINIAPP_TOOLCHAIN_STAGES = ["build", "preview", "upload", "review", "release"] as const;
export type MiniappToolchainStage = typeof MINIAPP_TOOLCHAIN_STAGES[number];
export type MiniappToolchainState = "NOT_RUN" | "BLOCKED" | "PASSED_EXTERNAL" | "FAILED_EXTERNAL" | "UNKNOWN_EXTERNAL";

export interface MiniappOfficialToolchainBinding {
  readonly platform: MiniappPlatform;
  readonly driver: "miniprogram-ci" | "minidev" | "douyin-developer-tools" | "xiaohongshu-developer-tools";
  readonly profileState: "BOUND_EXACT" | "BLOCKED_NO_EXACT_TUPLE";
  readonly stages: Readonly<Record<MiniappToolchainStage, string | null>>;
}

export interface MiniappToolchainStagePlan {
  readonly platform: MiniappPlatform;
  readonly platformVersion: string;
  readonly toolchainVersion: string;
  readonly driver: MiniappOfficialToolchainBinding["driver"];
  readonly stage: MiniappToolchainStage;
  readonly adapterAction: string | null;
  readonly projectDigest: string;
  readonly idempotencyKey: string;
  readonly state: "NOT_RUN" | "BLOCKED";
  readonly sideEffect: boolean;
  readonly approvalRequired: boolean;
  readonly reason: string;
}

export interface MiniappToolchainPermit {
  readonly schemaVersion: "1.0";
  readonly requestId: string;
  readonly tenantId: string;
  readonly platform: MiniappPlatform;
  readonly stage: MiniappToolchainStage;
  readonly projectDigest: string;
  readonly idempotencyKey: string;
  readonly credentialReference: string;
  readonly expiresAt: string;
  readonly approvalId?: string;
  readonly approvedBy?: string;
}

export interface MiniappToolchainReceipt {
  readonly schemaVersion: "1.0";
  readonly platform: MiniappPlatform;
  readonly stage: MiniappToolchainStage;
  readonly state: "PASSED" | "FAILED" | "UNKNOWN";
  readonly idempotencyKey: string;
  readonly projectDigest: string;
  readonly artifactDigest: `sha256:${string}` | null;
  readonly executor: string;
  readonly verifier: string;
  readonly startedAt: string;
  readonly completedAt: string;
  readonly rawReceiptDigest: `sha256:${string}`;
}

export interface MiniappToolchainBroker {
  execute(
    plan: MiniappToolchainStagePlan,
    permit: MiniappToolchainPermit,
  ): Promise<MiniappToolchainReceipt>;
}

export interface MiniappToolchainExecution {
  readonly state: MiniappToolchainState;
  readonly plan: MiniappToolchainStagePlan;
  readonly receipt: MiniappToolchainReceipt | null;
  readonly reason: string;
}

const BINDINGS: Readonly<Record<MiniappPlatform, MiniappOfficialToolchainBinding>> = {
  wechat: {
    platform: "wechat",
    driver: "miniprogram-ci",
    profileState: "BOUND_EXACT",
    stages: {
      build: "getCompiledResult",
      preview: "preview",
      upload: "upload",
      review: null,
      release: null,
    },
  },
  alipay: {
    platform: "alipay",
    driver: "minidev",
    profileState: "BOUND_EXACT",
    stages: {
      build: "minidev.build",
      preview: "minidev.preview",
      upload: "minidev.upload",
      review: null,
      release: null,
    },
  },
  douyin: {
    platform: "douyin",
    driver: "douyin-developer-tools",
    profileState: "BLOCKED_NO_EXACT_TUPLE",
    stages: { build: null, preview: null, upload: null, review: null, release: null },
  },
  xiaohongshu: {
    platform: "xiaohongshu",
    driver: "xiaohongshu-developer-tools",
    profileState: "BLOCKED_NO_EXACT_TUPLE",
    stages: { build: null, preview: null, upload: null, review: null, release: null },
  },
};

function digest(value: unknown): `sha256:${string}` {
  return miniappIrDigest(value) as `sha256:${string}`;
}

function isSideEffect(stage: MiniappToolchainStage): boolean {
  return stage === "upload" || stage === "review" || stage === "release";
}

export function miniappOfficialToolchainBinding(platform: MiniappPlatform): MiniappOfficialToolchainBinding {
  return BINDINGS[platform];
}

export function planMiniappOfficialToolchain(
  request: MiniappConversionRequest,
  projects: readonly MiniappGeneratedProject[],
): readonly MiniappToolchainStagePlan[] {
  return projects.flatMap(project => {
    const target = request.targets.find(candidate => candidate.platform === project.platform);
    if (!target) throw new Error(`missing exact target tuple for ${project.platform}`);
    const binding = BINDINGS[project.platform];
    return MINIAPP_TOOLCHAIN_STAGES.map(stage => {
      const adapterAction = binding.stages[stage];
      const sideEffect = isSideEffect(stage);
      const blocked = binding.profileState !== "BOUND_EXACT" || adapterAction === null;
      const identity = {
        requestId: request.requestId,
        tenantId: request.tenantId,
        platform: project.platform,
        platformVersion: target.platformVersion,
        toolchainVersion: target.toolchainVersion,
        projectDigest: project.deterministicDigest,
        stage,
      };
      return {
        platform: project.platform,
        platformVersion: target.platformVersion,
        toolchainVersion: target.toolchainVersion,
        driver: binding.driver,
        stage,
        adapterAction,
        projectDigest: project.deterministicDigest,
        idempotencyKey: digest(identity),
        state: blocked ? "BLOCKED" as const : "NOT_RUN" as const,
        sideEffect,
        approvalRequired: sideEffect || stage === "preview",
        reason: blocked
          ? binding.profileState === "BLOCKED_NO_EXACT_TUPLE"
            ? "No exact account-tested platform/toolchain tuple is bound."
            : "The official toolchain has no supported adapter action for this stage."
          : "Official execution requires an unexpired tenant-bound permit, credential reference and broker receipt.",
      };
    });
  });
}

function validateReceipt(plan: MiniappToolchainStagePlan, receipt: MiniappToolchainReceipt): void {
  if (
    receipt.schemaVersion !== "1.0"
    || receipt.platform !== plan.platform
    || receipt.stage !== plan.stage
    || receipt.idempotencyKey !== plan.idempotencyKey
    || receipt.projectDigest !== plan.projectDigest
  ) {
    throw new Error("official toolchain receipt is not bound to the exact plan");
  }
  if (!/^sha256:[0-9a-f]{64}$/u.test(receipt.rawReceiptDigest)) {
    throw new Error("official toolchain receipt digest is invalid");
  }
  if (receipt.state === "PASSED") {
    if (!receipt.artifactDigest || !/^sha256:[0-9a-f]{64}$/u.test(receipt.artifactDigest)) {
      throw new Error("passed official toolchain receipt lacks an artifact digest");
    }
    if (!receipt.executor || !receipt.verifier || receipt.executor === receipt.verifier) {
      throw new Error("passed official toolchain receipt lacks executor/verifier separation");
    }
  }
}

export async function executeMiniappOfficialToolchain(
  request: MiniappConversionRequest,
  plan: MiniappToolchainStagePlan,
  permit: MiniappToolchainPermit | undefined,
  broker: MiniappToolchainBroker | undefined,
): Promise<MiniappToolchainExecution> {
  if (plan.state === "BLOCKED") return { state: "BLOCKED", plan, receipt: null, reason: plan.reason };
  if (!permit || !broker) {
    return { state: "NOT_RUN", plan, receipt: null, reason: "Permit and official toolchain broker are required." };
  }
  const expiresAt = Date.parse(permit.expiresAt);
  if (
    permit.schemaVersion !== "1.0"
    || permit.requestId !== request.requestId
    || permit.tenantId !== request.tenantId
    || permit.platform !== plan.platform
    || permit.stage !== plan.stage
    || permit.projectDigest !== plan.projectDigest
    || permit.idempotencyKey !== plan.idempotencyKey
    || !permit.credentialReference.startsWith("secretref://")
    || !Number.isFinite(expiresAt)
    || expiresAt <= Date.now()
  ) {
    throw new Error("official toolchain permit is invalid, expired or cross-scope");
  }
  if (plan.approvalRequired && (!permit.approvalId || !permit.approvedBy)) {
    throw new Error(`official ${plan.stage} requires explicit approval`);
  }
  const receipt = await broker.execute(plan, permit);
  validateReceipt(plan, receipt);
  return {
    state: receipt.state === "PASSED" ? "PASSED_EXTERNAL"
      : receipt.state === "FAILED" ? "FAILED_EXTERNAL" : "UNKNOWN_EXTERNAL",
    plan,
    receipt,
    reason: `Official ${plan.driver} ${plan.stage} returned ${receipt.state}.`,
  };
}
