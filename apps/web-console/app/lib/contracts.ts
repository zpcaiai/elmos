export type CapabilityStatus = "READY" | "ENFORCED" | "BLOCKED" | "NOT_RUN" | "NOT_CONFIGURED" | "EXPERIMENTAL" | "REVIEW" | "DRAFT";

export type MigrationCapability = {
  id: string;
  batch: number;
  title: string;
  domain: string;
  description: string;
  skillCount: number;
  schemaCount: number;
  gateCommand: string;
  status: CapabilityStatus;
  icon: "code" | "workflow" | "database" | "layers" | "cloud" | "box" | "spark" | "shield";
  accent: "cyan" | "blue" | "violet" | "amber" | "green";
};

export type CapabilityResponse<T> = {
  source: "LIVE_API" | "REPOSITORY_CONTRACT";
  fetchedAt: string;
  externalExecutionEvidence: "NOT_RUN";
  capabilities: T[];
  note?: string;
};

export type ProductStage = {
  batch: string;
  shortTitle: string;
  title: string;
  subtitle: string;
  status: CapabilityStatus;
  icon: "shield" | "repository" | "server" | "file" | "lock";
  checks: Array<{ label: string; status: CapabilityStatus; detail: string }>;
  restrictions: string[];
};

export type ProductCapabilityResponse = {
  source: "LIVE_API" | "REPOSITORY_CONTRACT";
  fetchedAt: string;
  namespace: string;
  decisionCeiling: string;
  externalExecutionEvidence: "NOT_RUN";
  stages: ProductStage[];
  note?: string;
};

export type GenerationTargetId = "java" | "python" | "csharp";

export type GenerationTarget = {
  id: GenerationTargetId;
  language: string;
  runtime: string;
  framework: string;
  port: number;
  accent: "amber" | "blue" | "violet";
  icon: "code" | "spark" | "layers";
};

export type GenerationStage = {
  batch: string;
  title: string;
  detail: string;
};

export type GenerationCapabilityResponse = {
  source: "REPOSITORY_CONTRACT";
  fetchedAt: string;
  schemaVersion: "1.0.0";
  projectSkillCount: 170;
  targets: GenerationTarget[];
  stages: GenerationStage[];
  generationStatus: "NOT_RUN";
  externalExecutionEvidence: "NOT_RUN";
  productionDeliveryStatus: "NOT_RUN";
  certificationStatus: "NOT_CERTIFIED";
  note: string;
};
