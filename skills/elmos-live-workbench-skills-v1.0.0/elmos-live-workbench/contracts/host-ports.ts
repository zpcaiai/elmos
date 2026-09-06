/** Integration contracts only. Host must supply real auth/storage/sandbox implementations. */
export type Digest = `sha256:${string}`;
export type PreviewKind = 'web' | 'api' | 'cli' | 'library-test' | 'native-stream';
export type Capability = 'inspect' | 'control' | 'mutate' | 'host-exec';
export interface Binding {
  tenantId: string; repositoryId: string; snapshotId: Digest;
  sessionId: string; generation: number;
}
export interface VerifiedAuthority {
  /** Opaque handle from the existing host authority service; NEVER minted by browser/model. */
  handle: string; environmentId: string; capabilityLeaseId: string;
  expiresAt: number; binding: Binding; capabilities: readonly Capability[];
}
export interface SourceAnchor {
  snapshotId: Digest; path: string; blobDigest: Digest;
  byteStart: number; byteEnd: number; symbolId: string | null;
}
export interface RuntimeProfile {
  profileId: string; runtimeDigest: Digest; adapterDigest: Digest;
  language: string; framework: string; os: string; arch: string;
  previewKind: PreviewKind; qualificationEvidenceIds: readonly string[];
}
export interface ResourceBudget {
  executionSlots: number; cpuMillis: number; memoryMiB: number;
  diskMiB: number; pids: number; logBytes: number;
  prepareSeconds: 600; previewSeconds: 600; cleanupSeconds: 30;
}
export interface SandboxHandle {
  providerLeaseId: string; environmentId: string; generation: number;
  hardDeadline: number; privateEndpointHandle: string; // Not a public debug port.
}
export interface CleanupObservation {
  status: 'cleaned' | 'quarantined'; checks: Readonly<Record<string, boolean>>;
  observedAt: number; verifierId: string; evidenceIds: readonly string[];
}
export interface SandboxProvider {
  /** Reuses an atomically admitted resource group and the existing execution authority. */
  provision(authority: VerifiedAuthority, profile: RuntimeProfile, budget: ResourceBudget): Promise<SandboxHandle>;
  stageArtifact(handle: SandboxHandle, artifactDigest: Digest): Promise<void>;
  launchEntrypoint(handle: SandboxHandle, approvedEntrypointId: string): Promise<void>;
  enforceDeadline(handle: SandboxHandle, expiresAt: number): Promise<void>;
  terminateAndObserve(handle: SandboxHandle, reason: string): Promise<CleanupObservation>;
}
export interface ReadinessVerifier {
  /** MUST verify business behavior, artifact/revision binding, proxy authorization and capacity. */
  verify(authority: VerifiedAuthority, handle: SandboxHandle, scenarioId: string): Promise<{
    committedAttestationId: string; hostSignatureRef: string; firstReadyAt: number;
  }>;
}
export interface EvidencePort {
  ingestRaw(binding: Binding, payloadDigest: Digest): Promise<string>;
  intercept(rawId: string, authority: VerifiedAuthority): Promise<string>;
  commit(interceptedId: string, expectedGeneration: number): Promise<string>;
  /** Retrieval must authorize tenant/ACL/revision and redact before model exposure. */
  retrieveCommitted(authority: VerifiedAuthority, evidenceIds: readonly string[]): Promise<readonly unknown[]>;
}
export interface DebugEnvelope {
  binding: Binding; commandId: string; idempotencyKey: string;
  stopEpoch: number; controlLeaseId: string; command: string;
  arguments: Readonly<Record<string, unknown>>; deadline: number;
}
export interface DebugPort {
  negotiate(authority: VerifiedAuthority, handle: SandboxHandle): Promise<readonly string[]>;
  /** No generic shell fallback. Unknown effects must reconcile rather than retry. */
  submit(authority: VerifiedAuthority, command: DebugEnvelope): Promise<{
    state: 'committed' | 'pending' | 'unknown' | 'denied'; evidenceId?: string;
  }>;
  resumeReadOnly(authority: VerifiedAuthority, afterSequence: number): Promise<readonly unknown[]>;
}
export interface SourcePort {
  resolveImmutable(authority: VerifiedAuthority, anchor: SourceAnchor): Promise<string>;
  navigation(authority: VerifiedAuthority, symbolId: string, relation: string): Promise<readonly SourceAnchor[]>;
}
