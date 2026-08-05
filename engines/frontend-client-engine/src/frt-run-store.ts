import { createHash, randomUUID } from "node:crypto";
import {
  closeSync,
  existsSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";

import type {
  FrtExecutionScope,
  FrtSkillRunResult,
} from "./frt-types.js";

export interface FrtAuditEvent {
  readonly sequence: number;
  readonly at: string;
  readonly actor: string;
  readonly event:
    | "RUN_CREATED"
    | "RUN_CLAIMED"
    | "RUN_CANCELLED"
    | "RUN_RETRIED"
    | "RUN_COMPLETED"
    | "RUN_HEARTBEAT"
    | "RUN_LEASE_EXPIRED"
    | "RUN_RECOVERY_BLOCKED";
  readonly previousState: FrtSkillRunResult["state"] | null;
  readonly state: FrtSkillRunResult["state"];
  readonly version: number;
  readonly resultDigest: string;
}

export interface FrtStoredRun {
  readonly schemaVersion: "1.0";
  readonly organizationId: string;
  readonly tenantId: string;
  readonly runId: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly result: FrtSkillRunResult;
  readonly audit: readonly FrtAuditEvent[];
}

export interface FrtIdempotencyRecord {
  readonly schemaVersion: "1.0";
  readonly fingerprint: string;
  readonly runId: string;
}

export interface FrtRunStoreBackupEntry {
  readonly path: string;
  readonly byteCount: number;
  readonly sha256: string;
  readonly contentBase64: string;
}

export interface FrtRunStoreBackup {
  readonly schemaVersion: "1.0";
  readonly kind: "FRT_RUN_STORE_BACKUP";
  readonly createdAt: string;
  readonly entries: readonly FrtRunStoreBackupEntry[];
  readonly manifestDigest: string;
}

export interface FrtRunStore {
  getRun(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    runId: string,
  ): FrtStoredRun | undefined;
  saveRun(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    result: FrtSkillRunResult,
    options: {
      readonly actor: string;
      readonly event: FrtAuditEvent["event"];
      readonly expectedStoredVersion: number | null;
      readonly now: Date;
    },
  ): FrtStoredRun;
  getIdempotency(key: string): FrtIdempotencyRecord | undefined;
  saveIdempotency(key: string, value: FrtIdempotencyRecord): void;
  recoverableRuns(): readonly FrtStoredRun[];
}

export class FrtRunStoreError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "FrtRunStoreError";
    this.code = code;
  }
}

function hash(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function evidenceHash(value: string | Buffer): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

const backupPathPattern = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9._/-]{1,512}$/;
const evidenceDigestPattern = /^sha256:[a-f0-9]{64}$/;
const maximumBackupFiles = 100_000;
const maximumBackupBytes = 2 * 1024 * 1024 * 1024;

function safeStoreRoot(root: string): string {
  const resolved = resolve(root);
  if (resolved === resolve("/")) throw new FrtRunStoreError("FRT_RUN_STORE_ROOT_UNSAFE");
  if (existsSync(resolved) && lstatSync(resolved).isSymbolicLink()) {
    throw new FrtRunStoreError("FRT_RUN_STORE_ROOT_SYMLINK_REJECTED");
  }
  return resolved;
}

function backupEntries(root: string): readonly FrtRunStoreBackupEntry[] {
  if (!existsSync(root)) return [];
  const entries: FrtRunStoreBackupEntry[] = [];
  let totalBytes = 0;
  const visit = (directory: string): void => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const absolute = resolve(directory, entry.name);
      const relativePath = relative(root, absolute).split(sep).join("/");
      if (!backupPathPattern.test(relativePath)) {
        throw new FrtRunStoreError("FRT_BACKUP_PATH_INVALID");
      }
      if (entry.isSymbolicLink() || (!entry.isFile() && !entry.isDirectory())) {
        throw new FrtRunStoreError("FRT_BACKUP_SPECIAL_FILE_REJECTED");
      }
      if (entry.isDirectory()) {
        visit(absolute);
        continue;
      }
      if (relativePath.endsWith(".lock") || relativePath.includes(".tmp")) continue;
      const bytes = readFileSync(absolute);
      totalBytes += bytes.byteLength;
      if (entries.length >= maximumBackupFiles || totalBytes > maximumBackupBytes) {
        throw new FrtRunStoreError("FRT_BACKUP_LIMIT_EXCEEDED");
      }
      entries.push({
        path: relativePath,
        byteCount: bytes.byteLength,
        sha256: evidenceHash(bytes),
        contentBase64: bytes.toString("base64"),
      });
    }
  };
  visit(root);
  return entries.sort((left, right) => (left.path < right.path ? -1 : left.path > right.path ? 1 : 0));
}

function validateBackup(value: unknown): FrtRunStoreBackup {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new FrtRunStoreError("FRT_BACKUP_INVALID");
  }
  const backup = value as Partial<FrtRunStoreBackup>;
  if (backup.schemaVersion !== "1.0" || backup.kind !== "FRT_RUN_STORE_BACKUP"
      || typeof backup.createdAt !== "string" || Number.isNaN(Date.parse(backup.createdAt))
      || !Array.isArray(backup.entries) || backup.entries.length > maximumBackupFiles
      || typeof backup.manifestDigest !== "string" || !evidenceDigestPattern.test(backup.manifestDigest)) {
    throw new FrtRunStoreError("FRT_BACKUP_INVALID");
  }
  let totalBytes = 0;
  const seen = new Set<string>();
  for (const entry of backup.entries) {
    if (!entry || typeof entry !== "object" || !backupPathPattern.test(entry.path)
        || seen.has(entry.path) || !Number.isSafeInteger(entry.byteCount) || entry.byteCount < 0
        || typeof entry.sha256 !== "string" || !evidenceDigestPattern.test(entry.sha256)
        || typeof entry.contentBase64 !== "string") {
      throw new FrtRunStoreError("FRT_BACKUP_ENTRY_INVALID");
    }
    const bytes = Buffer.from(entry.contentBase64, "base64");
    totalBytes += bytes.byteLength;
    if (bytes.byteLength !== entry.byteCount || evidenceHash(bytes) !== entry.sha256
        || totalBytes > maximumBackupBytes) {
      throw new FrtRunStoreError("FRT_BACKUP_DIGEST_MISMATCH");
    }
    seen.add(entry.path);
  }
  if (evidenceHash(canonical(backup.entries)) !== backup.manifestDigest) {
    throw new FrtRunStoreError("FRT_BACKUP_MANIFEST_MISMATCH");
  }
  return backup as FrtRunStoreBackup;
}

export function backupFrtRunStore(
  sourceRoot: string,
  backupPath: string,
  now = new Date(),
): FrtRunStoreBackup {
  const source = safeStoreRoot(sourceRoot);
  const destination = resolve(backupPath);
  if (destination === resolve("/") || destination === source
      || destination.startsWith(`${source}${sep}`)) {
    throw new FrtRunStoreError("FRT_BACKUP_DESTINATION_UNSAFE");
  }
  const entries = backupEntries(source);
  const backup: FrtRunStoreBackup = {
    schemaVersion: "1.0",
    kind: "FRT_RUN_STORE_BACKUP",
    createdAt: now.toISOString(),
    entries,
    manifestDigest: evidenceHash(canonical(entries)),
  };
  atomicJson(destination, backup);
  return backup;
}

export function restoreFrtRunStore(
  backupPath: string,
  targetRoot: string,
): { readonly entryCount: number; readonly manifestDigest: string } {
  const source = resolve(backupPath);
  const target = safeStoreRoot(targetRoot);
  if (!existsSync(source) || existsSync(target) || target === source || target.startsWith(`${source}${sep}`)) {
    throw new FrtRunStoreError("FRT_RESTORE_TARGET_UNSAFE");
  }
  const parsed = parseJson<unknown>(source);
  const backup = validateBackup(parsed);
  const staging = resolve(dirname(target), `.${hash(target)}.${randomUUID()}.restore`);
  try {
    mkdirSync(staging, { recursive: false, mode: 0o700 });
    for (const entry of backup.entries) {
      const destination = resolve(staging, entry.path);
      if (!destination.startsWith(`${staging}${sep}`)) {
        throw new FrtRunStoreError("FRT_RESTORE_PATH_ESCAPE");
      }
      mkdirSync(dirname(destination), { recursive: true, mode: 0o700 });
      writeFileSync(destination, Buffer.from(entry.contentBase64, "base64"), { flag: "wx", mode: 0o600 });
    }
    renameSync(staging, target);
  } catch (error) {
    if (existsSync(staging)) rmSync(staging, { recursive: true, force: true });
    throw error;
  }
  return { entryCount: backup.entries.length, manifestDigest: backup.manifestDigest };
}

function parseJson<T>(path: string): T | undefined {
  try {
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return undefined;
  }
}

function atomicJson(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = `${path}.${randomUUID()}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  renameSync(temporary, path);
}

function withLock<T>(path: string, operation: () => T): T {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  let descriptor: number;
  try {
    descriptor = openSync(path, "wx", 0o600);
  } catch {
    throw new FrtRunStoreError("FRT_RUN_STORE_CONCURRENT_MUTATION");
  }
  try {
    return operation();
  } finally {
    closeSync(descriptor);
    try {
      unlinkSync(path);
    } catch {
      // A missing lock after a successful close is safe; the data file remains authoritative.
    }
  }
}

export class FileFrtRunStore implements FrtRunStore {
  readonly #root: string;

  constructor(root: string) {
    this.#root = safeStoreRoot(root);
  }

  #tenantDirectory(scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">): string {
    return resolve(this.#root, "tenants", hash(`${scope.organizationId}\u0000${scope.tenantId}`));
  }

  #runPath(scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">, runId: string): string {
    return resolve(this.#tenantDirectory(scope), "runs", `${hash(runId)}.json`);
  }

  getRun(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    runId: string,
  ): FrtStoredRun | undefined {
    const stored = parseJson<FrtStoredRun>(this.#runPath(scope, runId));
    if (!stored || stored.schemaVersion !== "1.0" || stored.runId !== runId
        || stored.organizationId !== scope.organizationId || stored.tenantId !== scope.tenantId) {
      return undefined;
    }
    return stored;
  }

  saveRun(
    scope: Pick<FrtExecutionScope, "organizationId" | "tenantId">,
    result: FrtSkillRunResult,
    options: {
      readonly actor: string;
      readonly event: FrtAuditEvent["event"];
      readonly expectedStoredVersion: number | null;
      readonly now: Date;
    },
  ): FrtStoredRun {
    const path = this.#runPath(scope, result.runId);
    return withLock(`${path}.lock`, () => {
      const existing = this.getRun(scope, result.runId);
      if ((existing?.result.version ?? null) !== options.expectedStoredVersion) {
        throw new FrtRunStoreError("FRT_RUN_VERSION_CONFLICT");
      }
      const at = options.now.toISOString();
      const audit: FrtAuditEvent = {
        sequence: (existing?.audit.length ?? 0) + 1,
        at,
        actor: options.actor,
        event: options.event,
        previousState: existing?.result.state ?? null,
        state: result.state,
        version: result.version,
        resultDigest: result.resultDigest,
      };
      const stored: FrtStoredRun = {
        schemaVersion: "1.0",
        organizationId: scope.organizationId,
        tenantId: scope.tenantId,
        runId: result.runId,
        createdAt: existing?.createdAt ?? at,
        updatedAt: at,
        result,
        audit: [...(existing?.audit ?? []), audit],
      };
      atomicJson(path, stored);
      return stored;
    });
  }

  getIdempotency(key: string): FrtIdempotencyRecord | undefined {
    const stored = parseJson<FrtIdempotencyRecord>(
      resolve(this.#root, "idempotency", `${hash(key)}.json`),
    );
    return stored?.schemaVersion === "1.0" ? stored : undefined;
  }

  saveIdempotency(key: string, value: FrtIdempotencyRecord): void {
    const path = resolve(this.#root, "idempotency", `${hash(key)}.json`);
    withLock(`${path}.lock`, () => {
      const existing = this.getIdempotency(key);
      if (existing && (existing.fingerprint !== value.fingerprint || existing.runId !== value.runId)) {
        throw new FrtRunStoreError("FRT_IDEMPOTENCY_CONFLICT");
      }
      if (!existing) atomicJson(path, value);
    });
  }

  recoverableRuns(): readonly FrtStoredRun[] {
    const tenants = resolve(this.#root, "tenants");
    if (!existsSync(tenants)) return [];
    const stored: FrtStoredRun[] = [];
    for (const tenant of readdirSync(tenants, { withFileTypes: true })) {
      if (!tenant.isDirectory()) continue;
      const runs = resolve(tenants, tenant.name, "runs");
      if (!existsSync(runs)) continue;
      for (const entry of readdirSync(runs, { withFileTypes: true })) {
        if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
        const record = parseJson<FrtStoredRun>(resolve(runs, entry.name));
        if (record && ["QUEUED", "RUNNING"].includes(record.result.state)) stored.push(record);
      }
    }
    return stored;
  }
}

export function frtRunStoreFromEnvironment(): FrtRunStore {
  return new FileFrtRunStore(
    process.env.ELMOS_FRT_RUN_STORE_ROOT?.trim()
      || resolve(process.cwd(), ".elmos", "frt-run-store"),
  );
}
