import { createHash, randomUUID } from "node:crypto";
import {
  mkdir,
  open,
  readFile,
  readdir,
  rename,
  rm,
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

export class DurableLeaseError extends Error {
  constructor(
    readonly code:
      | "QUEUE_ITEM_EXPIRED"
      | "QUEUE_GLOBAL_CAPACITY_REACHED"
      | "QUEUE_TENANT_CAPACITY_REACHED"
      | "QUEUE_JOB_ALREADY_LEASED"
      | "QUEUE_CONTROL_LOCK_UNAVAILABLE"
      | "QUEUE_LEASE_LOST",
    readonly retryable: boolean,
  ) {
    super(code);
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

async function withControlLock<T>(
  configuration: DurableLeaseConfiguration,
  operation: () => Promise<T>,
): Promise<T> {
  const controlRoot = confined(configuration.root, ".durable-queue", "control");
  await mkdir(controlRoot, { recursive: true, mode: 0o700 });
  const lockPath = confined(controlRoot, `${configuration.line}.lock`);
  const deadline = Date.now() + 5_000;
  while (Date.now() < deadline) {
    try {
      const handle = await open(lockPath, "wx", 0o600);
      try {
        await handle.writeFile(`${process.pid}:${Date.now()}\n`);
        return await operation();
      } finally {
        await handle.close();
        await rm(lockPath, { force: true });
      }
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error
        ? String(error.code)
        : "";
      if (code !== "EEXIST") throw error;
      try {
        const raw = await readFile(lockPath, "utf8");
        const timestamp = Number(raw.trim().split(":").at(-1));
        if (Number.isFinite(timestamp) && Date.now() - timestamp > 15_000) {
          await rename(lockPath, `${lockPath}.stale.${randomUUID()}`);
          continue;
        }
      } catch {
        // Another process may have just released the lock.
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
    await withControlLock(configuration, async () => {
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

  get heartbeatIntervalMs(): number {
    return Math.max(10_000, Math.floor(this.#configuration.leaseTtlMs / 3));
  }

  async heartbeat(): Promise<void> {
    if (this.#released) throw new DurableLeaseError("QUEUE_LEASE_LOST", false);
    await withControlLock(this.#configuration, async () => {
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
    await withControlLock(this.#configuration, async () => {
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
