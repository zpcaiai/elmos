import { createHash, randomUUID } from "node:crypto";
import { hostname } from "node:os";
import {
  mkdir,
  open,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";

const jobIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const linePattern = /^[a-z][a-z0-9-]{2,40}$/;
const digestPattern = /^[0-9a-f]{64}$/;

type LeaseDocument = {
  schemaVersion: "1.0";
  line: string;
  tenantDigest: string;
  jobId: string;
  ownerId: string;
  inputDigest: string;
  acquiredAt: string;
  heartbeatAt: string;
  expiresAt: string;
};

type ControlLockDocument = {
  schemaVersion: "1.0";
  line: string;
  ownerToken: string;
  hostname: string;
  pid: number;
  createdAt: string;
  heartbeatAt: string;
  legacy?: true;
};

type ControlLockObservation = {
  raw: string;
  document?: ControlLockDocument;
  modifiedAtMs: number;
};

const controlLockStaleMs = 15_000;
const controlLockHeartbeatMs = 5_000;

export class DurableLeaseError extends Error {
  readonly code:
    | "QUEUE_ITEM_EXPIRED"
    | "QUEUE_GLOBAL_CAPACITY_REACHED"
    | "QUEUE_TENANT_CAPACITY_REACHED"
    | "QUEUE_JOB_ALREADY_LEASED"
    | "QUEUE_CONTROL_LOCK_UNAVAILABLE"
    | "QUEUE_LEASE_LOST";
  readonly retryable: boolean;

  constructor(
    code:
      | "QUEUE_ITEM_EXPIRED"
      | "QUEUE_GLOBAL_CAPACITY_REACHED"
      | "QUEUE_TENANT_CAPACITY_REACHED"
      | "QUEUE_JOB_ALREADY_LEASED"
      | "QUEUE_CONTROL_LOCK_UNAVAILABLE"
      | "QUEUE_LEASE_LOST",
    retryable: boolean,
  ) {
    super(code);
    this.code = code;
    this.retryable = retryable;
  }
}

export type DurableLeaseConfiguration = {
  root: string;
  line: string;
  globalCapacity: number;
  tenantCapacity: number;
  queueTtlMs: number;
  leaseTtlMs: number;
};

export type DurableJobLeaseObservation = {
  active: boolean;
  ownerId?: string;
  acquiredAt?: string;
  heartbeatAt?: string;
  expiresAt?: string;
  inputDigestMatches?: boolean;
};

function assertConfiguration(configuration: DurableLeaseConfiguration) {
  if (!path.isAbsolute(configuration.root)
    || path.resolve(configuration.root) === path.parse(configuration.root).root
    || !linePattern.test(configuration.line)
    || configuration.globalCapacity < 1 || configuration.globalCapacity > 1_000
    || configuration.tenantCapacity < 1
    || configuration.tenantCapacity > configuration.globalCapacity
    || configuration.queueTtlMs < 60_000 || configuration.queueTtlMs > 30 * 24 * 60 * 60_000
    || configuration.leaseTtlMs < 30_000 || configuration.leaseTtlMs > 60 * 60_000) {
    throw new Error("DURABLE_QUEUE_CONFIGURATION_INVALID");
  }
}

function digest(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function confined(root: string, ...segments: string[]): string {
  const resolvedRoot = path.resolve(root);
  const candidate = path.resolve(resolvedRoot, ...segments);
  if (candidate !== resolvedRoot && !candidate.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw new Error("DURABLE_QUEUE_PATH_ESCAPE");
  }
  return candidate;
}

async function atomicJson(destination: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
  const temporary = `${destination}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, {
    mode: 0o600,
    flag: "wx",
  });
  await rename(temporary, destination);
}

function parseControlLock(raw: string, expectedLine: string): ControlLockDocument | undefined {
  try {
    const value = JSON.parse(raw) as Partial<ControlLockDocument>;
    if (
      value.schemaVersion !== "1.0"
      || value.line !== expectedLine
      || !value.ownerToken?.match(jobIdPattern)
      || typeof value.hostname !== "string"
      || value.hostname.length < 1
      || value.hostname.length > 253
      || /[\0\r\n]/.test(value.hostname)
      || !Number.isSafeInteger(value.pid)
      || Number(value.pid) <= 0
      || Number(value.pid) > 2_147_483_647
      || !Number.isFinite(Date.parse(value.createdAt ?? ""))
      || !Number.isFinite(Date.parse(value.heartbeatAt ?? ""))
    ) return undefined;
    return value as ControlLockDocument;
  } catch {
    const legacy = /^(\d{1,10}):(\d{10,16})$/.exec(raw.trim());
    if (!legacy) return undefined;
    const pid = Number.parseInt(legacy[1], 10);
    const timestamp = Number.parseInt(legacy[2], 10);
    if (
      !Number.isSafeInteger(pid)
      || pid <= 0
      || pid > 2_147_483_647
      || !Number.isSafeInteger(timestamp)
      || timestamp < 0
      || timestamp > 8_640_000_000_000_000
    ) return undefined;
    const at = new Date(timestamp).toISOString();
    return {
      schemaVersion: "1.0",
      line: expectedLine,
      ownerToken: `00000000-0000-4000-8000-${digest(raw).slice(0, 12)}`,
      hostname: hostname(),
      pid,
      createdAt: at,
      heartbeatAt: at,
      legacy: true,
    };
  }
}

function processIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code !== "ESRCH";
  }
}

async function observeControlLock(
  lockPath: string,
  expectedLine: string,
): Promise<ControlLockObservation> {
  const handle = await open(lockPath, "r");
  try {
    const raw = await handle.readFile("utf8");
    const descriptorState = await handle.stat();
    const canonicalState = await stat(lockPath);
    if (
      descriptorState.dev !== canonicalState.dev
      || descriptorState.ino !== canonicalState.ino
    ) throw new DurableLeaseError("QUEUE_CONTROL_LOCK_UNAVAILABLE", true);
    return {
      raw,
      document: parseControlLock(raw, expectedLine),
      modifiedAtMs: descriptorState.mtimeMs,
    };
  } finally {
    await handle.close();
  }
}

function controlLockIsReclaimable(observation: ControlLockObservation): boolean {
  // The predecessor format has no host or owner token. Reclaiming it could let
  // its still-live owner unlink a successor lock, so upgrades fail closed until
  // that short critical section exits or an operator verifies the old process.
  if (observation.document?.legacy) return false;
  const lastActivity = observation.document
    ? Date.parse(observation.document.heartbeatAt)
    : observation.modifiedAtMs;
  if (!Number.isFinite(lastActivity) || Date.now() - lastActivity <= controlLockStaleMs) {
    return false;
  }
  if (
    observation.document?.hostname === hostname()
    && processIsAlive(observation.document.pid)
  ) return false;
  return true;
}

async function restoreMovedControlLock(
  movedPath: string,
  lockPath: string,
  raw: string,
): Promise<boolean> {
  try {
    const handle = await open(lockPath, "wx", 0o600);
    try {
      await handle.writeFile(raw);
      await handle.sync();
    } finally {
      await handle.close();
    }
    await rm(movedPath, { force: true });
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    try {
      if (await readFile(lockPath, "utf8") === raw) {
        await rm(movedPath, { force: true });
        return true;
      }
    } catch {
      // The canonical owner changed again; retain the moved file for diagnosis.
    }
    return false;
  }
}

async function reclaimControlLock(
  lockPath: string,
  observation: ControlLockObservation,
): Promise<boolean> {
  const movedPath = `${lockPath}.stale.${randomUUID()}`;
  try {
    await rename(lockPath, movedPath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
  const movedRaw = await readFile(movedPath, "utf8");
  if (movedRaw !== observation.raw) {
    await restoreMovedControlLock(movedPath, lockPath, movedRaw);
    throw new DurableLeaseError("QUEUE_CONTROL_LOCK_UNAVAILABLE", true);
  }
  await rm(movedPath, { force: true });
  return true;
}

async function refreshControlLock(
  lockPath: string,
  expectedLine: string,
  ownerToken: string,
): Promise<void> {
  const handle = await open(lockPath, "r+");
  try {
    const raw = await handle.readFile("utf8");
    const current = parseControlLock(raw, expectedLine);
    if (current?.ownerToken !== ownerToken) {
      throw new DurableLeaseError("QUEUE_CONTROL_LOCK_UNAVAILABLE", true);
    }
    const descriptorState = await handle.stat();
    const payload = Buffer.from(`${JSON.stringify({
      ...current,
      heartbeatAt: new Date().toISOString(),
    } satisfies ControlLockDocument, null, 2)}\n`);
    await handle.truncate(0);
    await handle.write(payload, 0, payload.length, 0);
    await handle.sync();
    const canonicalState = await stat(lockPath);
    if (
      descriptorState.dev !== canonicalState.dev
      || descriptorState.ino !== canonicalState.ino
    ) throw new DurableLeaseError("QUEUE_CONTROL_LOCK_UNAVAILABLE", true);
  } finally {
    await handle.close();
  }
}

async function releaseControlLock(
  lockPath: string,
  expectedLine: string,
  ownerToken: string,
): Promise<boolean> {
  let observation: ControlLockObservation;
  try {
    observation = await observeControlLock(lockPath, expectedLine);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
  if (observation.document?.ownerToken !== ownerToken) return false;
  const movedPath = `${lockPath}.release.${ownerToken}.${randomUUID()}`;
  try {
    await rename(lockPath, movedPath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
  const movedRaw = await readFile(movedPath, "utf8");
  const moved = parseControlLock(movedRaw, expectedLine);
  if (moved?.ownerToken !== ownerToken) {
    await restoreMovedControlLock(movedPath, lockPath, movedRaw);
    return false;
  }
  await rm(movedPath, { force: true });
  return true;
}

export async function withDurableQueueControlLock<T>(
  configuration: DurableLeaseConfiguration,
  operation: () => Promise<T>,
): Promise<T> {
  assertConfiguration(configuration);
  const controlRoot = confined(configuration.root, ".durable-queue", "control");
  await mkdir(controlRoot, { recursive: true, mode: 0o700 });
  const lockPath = confined(controlRoot, `${configuration.line}.lock`);
  const deadline = Date.now() + 5_000;
  while (Date.now() < deadline) {
    try {
      const now = new Date();
      const ownerToken = randomUUID();
      const document: ControlLockDocument = {
        schemaVersion: "1.0",
        line: configuration.line,
        ownerToken,
        hostname: hostname(),
        pid: process.pid,
        createdAt: now.toISOString(),
        heartbeatAt: now.toISOString(),
      };
      const handle = await open(lockPath, "wx", 0o600);
      try {
        await handle.writeFile(`${JSON.stringify(document, null, 2)}\n`);
        await handle.sync();
      } finally {
        await handle.close();
      }
      let heartbeatFailure: unknown;
      let heartbeatTail = Promise.resolve();
      const heartbeat = setInterval(() => {
        heartbeatTail = heartbeatTail
          .then(() => refreshControlLock(lockPath, configuration.line, ownerToken))
          .catch((error: unknown) => {
            heartbeatFailure ??= error;
          });
      }, controlLockHeartbeatMs);
      heartbeat.unref();
      try {
        const result = await operation();
        await heartbeatTail;
        if (heartbeatFailure) {
          throw new DurableLeaseError("QUEUE_CONTROL_LOCK_UNAVAILABLE", true);
        }
        return result;
      } finally {
        clearInterval(heartbeat);
        await heartbeatTail;
        if (!await releaseControlLock(lockPath, configuration.line, ownerToken)) {
          throw new DurableLeaseError("QUEUE_CONTROL_LOCK_UNAVAILABLE", true);
        }
      }
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error
        ? String(error.code)
        : "";
      if (code !== "EEXIST") throw error;
      try {
        const observation = await observeControlLock(lockPath, configuration.line);
        if (controlLockIsReclaimable(observation)) {
          await reclaimControlLock(lockPath, observation);
          continue;
        }
      } catch (error) {
        const canonicalOwnerChanged = (
          error instanceof DurableLeaseError
          && error.code === "QUEUE_CONTROL_LOCK_UNAVAILABLE"
          && error.retryable
        );
        if ((error as NodeJS.ErrnoException).code !== "ENOENT" && !canonicalOwnerChanged) {
          throw error;
        }
        // Another owner released or replaced the canonical path between
        // observation steps. Keep this transient lock churn inside the bounded
        // retry loop instead of leaking it to a same-job contender.
      }
      await new Promise((resolve) => setTimeout(resolve, 25 + Math.floor(Math.random() * 50)));
    }
  }
  throw new DurableLeaseError("QUEUE_CONTROL_LOCK_UNAVAILABLE", true);
}

function parseLease(raw: string, expectedLine: string): LeaseDocument {
  const value = JSON.parse(raw) as Partial<LeaseDocument>;
  if (
    value.schemaVersion !== "1.0"
    || value.line !== expectedLine
    || !value.tenantDigest?.match(digestPattern)
    || !value.jobId?.match(jobIdPattern)
    || !value.ownerId || value.ownerId.length > 160
    || !value.inputDigest?.match(digestPattern)
    || !value.acquiredAt || !value.heartbeatAt || !value.expiresAt
    || !Number.isFinite(Date.parse(value.expiresAt))
  ) {
    throw new Error("DURABLE_QUEUE_LEASE_INVALID");
  }
  return value as LeaseDocument;
}

async function activeLeases(configuration: DurableLeaseConfiguration): Promise<LeaseDocument[]> {
  const leasesRoot = confined(
    configuration.root, ".durable-queue", "leases", configuration.line,
  );
  const deadRoot = confined(
    configuration.root, ".durable-queue", "dead-letter", configuration.line,
  );
  await mkdir(leasesRoot, { recursive: true, mode: 0o700 });
  await mkdir(deadRoot, { recursive: true, mode: 0o700 });
  const result: LeaseDocument[] = [];
  for (const tenantEntry of await readdir(leasesRoot, { withFileTypes: true })) {
    if (!tenantEntry.isDirectory() || !tenantEntry.name.match(digestPattern)) continue;
    const tenantRoot = confined(leasesRoot, tenantEntry.name);
    for (const entry of await readdir(tenantRoot, { withFileTypes: true })) {
      if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
      const source = confined(tenantRoot, entry.name);
      let lease: LeaseDocument;
      try {
        lease = parseLease(await readFile(source, "utf8"), configuration.line);
      } catch {
        const quarantine = confined(deadRoot, `corrupt-${randomUUID()}.json`);
        await rename(source, quarantine);
        continue;
      }
      if (Date.parse(lease.expiresAt) <= Date.now()) {
        const quarantine = confined(
          deadRoot, `expired-${lease.tenantDigest}-${lease.jobId}-${randomUUID()}.json`,
        );
        await rename(source, quarantine);
        continue;
      }
      result.push(lease);
    }
  }
  return result;
}

export class DurableJobLease implements AsyncDisposable {
  readonly ownerId: string;
  readonly #configuration: DurableLeaseConfiguration;
  readonly #tenantDigest: string;
  readonly #jobId: string;
  readonly #inputDigest: string;
  #released = false;

  private constructor(
    configuration: DurableLeaseConfiguration,
    tenantDigest: string,
    jobId: string,
    inputDigest: string,
    ownerId: string,
  ) {
    this.#configuration = configuration;
    this.#tenantDigest = tenantDigest;
    this.#jobId = jobId;
    this.#inputDigest = inputDigest;
    this.ownerId = ownerId;
  }

  static async acquire(input: {
    configuration: DurableLeaseConfiguration;
    tenantId: string;
    jobId: string;
    createdAt: string;
    inputDigest: string;
  }): Promise<DurableJobLease> {
    const configuration = { ...input.configuration, root: path.resolve(input.configuration.root) };
    assertConfiguration(configuration);
    if (!jobIdPattern.test(input.jobId) || !digestPattern.test(input.inputDigest)) {
      throw new Error("DURABLE_QUEUE_JOB_IDENTITY_INVALID");
    }
    const createdAt = Date.parse(input.createdAt);
    if (!Number.isFinite(createdAt) || Date.now() - createdAt > configuration.queueTtlMs) {
      throw new DurableLeaseError("QUEUE_ITEM_EXPIRED", false);
    }
    const tenantDigest = digest(input.tenantId);
    const ownerId = `${process.pid}-${randomUUID()}`;
    await withDurableQueueControlLock(configuration, async () => {
      const active = await activeLeases(configuration);
      if (active.some((lease) => lease.jobId === input.jobId)) {
        throw new DurableLeaseError("QUEUE_JOB_ALREADY_LEASED", true);
      }
      if (active.length >= configuration.globalCapacity) {
        throw new DurableLeaseError("QUEUE_GLOBAL_CAPACITY_REACHED", true);
      }
      if (active.filter((lease) => lease.tenantDigest === tenantDigest).length
        >= configuration.tenantCapacity) {
        throw new DurableLeaseError("QUEUE_TENANT_CAPACITY_REACHED", true);
      }
      const now = new Date();
      const document: LeaseDocument = {
        schemaVersion: "1.0",
        line: configuration.line,
        tenantDigest,
        jobId: input.jobId,
        ownerId,
        inputDigest: input.inputDigest,
        acquiredAt: now.toISOString(),
        heartbeatAt: now.toISOString(),
        expiresAt: new Date(now.getTime() + configuration.leaseTtlMs).toISOString(),
      };
      const leasePath = confined(
        configuration.root, ".durable-queue", "leases", configuration.line,
        tenantDigest, `${input.jobId}.json`,
      );
      await mkdir(path.dirname(leasePath), { recursive: true, mode: 0o700 });
      const handle = await open(leasePath, "wx", 0o600);
      try {
        await handle.writeFile(`${JSON.stringify(document, null, 2)}\n`);
      } finally {
        await handle.close();
      }
    });
    return new DurableJobLease(
      configuration, tenantDigest, input.jobId, input.inputDigest, ownerId,
    );
  }

  static async observe(input: {
    configuration: DurableLeaseConfiguration;
    tenantId: string;
    jobId: string;
    inputDigest: string;
  }): Promise<DurableJobLeaseObservation> {
    const configuration = { ...input.configuration, root: path.resolve(input.configuration.root) };
    assertConfiguration(configuration);
    if (!jobIdPattern.test(input.jobId) || !digestPattern.test(input.inputDigest)) {
      throw new Error("DURABLE_QUEUE_JOB_IDENTITY_INVALID");
    }
    const tenantDigest = digest(input.tenantId);
    return withDurableQueueControlLock(configuration, async () => {
      const lease = (await activeLeases(configuration)).find((candidate) => (
        candidate.jobId === input.jobId && candidate.tenantDigest === tenantDigest
      ));
      if (!lease) return { active: false };
      return {
        active: true,
        ownerId: lease.ownerId,
        acquiredAt: lease.acquiredAt,
        heartbeatAt: lease.heartbeatAt,
        expiresAt: lease.expiresAt,
        inputDigestMatches: lease.inputDigest === input.inputDigest,
      };
    });
  }

  get heartbeatIntervalMs(): number {
    return Math.max(10_000, Math.floor(this.#configuration.leaseTtlMs / 3));
  }

  async heartbeat(): Promise<void> {
    if (this.#released) throw new DurableLeaseError("QUEUE_LEASE_LOST", false);
    await withDurableQueueControlLock(this.#configuration, async () => {
      const leasePath = this.#leasePath();
      const lease = parseLease(await readFile(leasePath, "utf8"), this.#configuration.line);
      if (
        lease.ownerId !== this.ownerId
        || lease.inputDigest !== this.#inputDigest
        || lease.tenantDigest !== this.#tenantDigest
        || Date.parse(lease.expiresAt) <= Date.now()
      ) {
        throw new DurableLeaseError("QUEUE_LEASE_LOST", false);
      }
      const now = new Date();
      await atomicJson(leasePath, {
        ...lease,
        heartbeatAt: now.toISOString(),
        expiresAt: new Date(now.getTime() + this.#configuration.leaseTtlMs).toISOString(),
      } satisfies LeaseDocument);
    });
  }

  async release(outcome: "SUCCEEDED" | "FAILED" | "BLOCKED" | "CANCELLED"): Promise<void> {
    if (this.#released) return;
    await withDurableQueueControlLock(this.#configuration, async () => {
      const leasePath = this.#leasePath();
      const lease = parseLease(await readFile(leasePath, "utf8"), this.#configuration.line);
      if (lease.ownerId !== this.ownerId || lease.inputDigest !== this.#inputDigest) {
        throw new DurableLeaseError("QUEUE_LEASE_LOST", false);
      }
      const receiptPath = confined(
        this.#configuration.root, ".durable-queue", "receipts",
        this.#configuration.line, this.#tenantDigest, `${this.#jobId}.json`,
      );
      await atomicJson(receiptPath, {
        ...lease,
        releasedAt: new Date().toISOString(),
        outcome,
      });
      await rm(leasePath);
      this.#released = true;
    });
  }

  async [Symbol.asyncDispose](): Promise<void> {
    if (!this.#released) await this.release("BLOCKED");
  }

  #leasePath(): string {
    return confined(
      this.#configuration.root, ".durable-queue", "leases",
      this.#configuration.line, this.#tenantDigest, `${this.#jobId}.json`,
    );
  }
}

export function durableQueueConfiguration(
  root: string,
  line: string,
): DurableLeaseConfiguration {
  const prefix = `ELMOS_${line.toUpperCase().replaceAll("-", "_")}`;
  const integer = (name: string, fallback: number) => {
    const value = Number.parseInt(process.env[`${prefix}_${name}`] ?? "", 10);
    return Number.isFinite(value) ? value : fallback;
  };
  return {
    root,
    line,
    globalCapacity: integer("GLOBAL_CAPACITY", 2),
    tenantCapacity: integer("TENANT_CAPACITY", 1),
    queueTtlMs: integer("QUEUE_TTL_SECONDS", 3_600) * 1_000,
    leaseTtlMs: integer("LEASE_TTL_SECONDS", 120) * 1_000,
  };
}
