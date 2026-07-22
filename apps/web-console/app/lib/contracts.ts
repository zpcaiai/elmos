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
