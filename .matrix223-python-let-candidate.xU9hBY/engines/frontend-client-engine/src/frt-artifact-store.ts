import { createHash } from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { randomUUID } from "node:crypto";
import { dirname, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import type { FrtRunnerArtifactReference } from "./frt-types.js";

/**
 * Content-addressed artifact store.
 *
 * Generated target workspaces and runner outputs are written here and referenced by
 * digest, never by caller-supplied path: a name can therefore neither collide nor
 * escape the approved root, and writing the same bytes twice is a no-op instead of a
 * silent overwrite. Objects are immutable once written.
 *
 * URIs are plain `file:` URLs, so an artifact root that is also listed in
 * ELMOS_FRT_EVIDENCE_ROOTS can back evidence references without a second resolver.
 */
export interface FrtArtifactStore {
  put(name: string, bytes: Buffer): FrtRunnerArtifactReference;
  resolve(uri: string): Buffer;
  list(): readonly FrtStoredArtifact[];
  archiveGarbage(policy: FrtArtifactLifecyclePolicy): FrtArtifactLifecycleReport;
  readonly configured: boolean;
}

export interface FrtStoredArtifact {
  readonly digest: string;
  readonly uri: string;
  readonly byteCount: number;
  readonly modifiedAt: string;
}

/**
 * Lifecycle is explicit and recoverable. Callers supply the complete live digest set;
 * objects are moved below `archive/`, never deleted. A later, separately authorized
 * retention process may remove an archive after its own review window.
 */
export interface FrtArtifactLifecyclePolicy {
  readonly liveDigests: readonly string[];
  readonly minimumAgeSeconds?: number;
  readonly retentionSeconds?: number;
  readonly maximumActiveBytes?: number;
  readonly now?: Date;
}

export interface FrtArtifactLifecycleReport {
  readonly activeBytesBefore: number;
  readonly activeBytesAfter: number;
  readonly activeObjectsBefore: number;
  readonly activeObjectsAfter: number;
  readonly archived: readonly FrtStoredArtifact[];
  readonly quotaSatisfied: boolean;
  readonly recoveryRoot: string | null;
}

export class FrtArtifactStoreError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "FrtArtifactStoreError";
    this.code = code;
  }
}

const artifactName = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const digestPattern = /^sha256:[a-f0-9]{64}$/;

function digestOf(bytes: Buffer): string {
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

export class DenyAllFrtArtifactStore implements FrtArtifactStore {
  readonly configured = false;

  put(): FrtRunnerArtifactReference {
    throw new FrtArtifactStoreError("FRT_ARTIFACT_STORE_NOT_CONFIGURED");
  }

  resolve(): Buffer {
    throw new FrtArtifactStoreError("FRT_ARTIFACT_STORE_NOT_CONFIGURED");
  }

  list(): readonly FrtStoredArtifact[] {
    throw new FrtArtifactStoreError("FRT_ARTIFACT_STORE_NOT_CONFIGURED");
  }

  archiveGarbage(): FrtArtifactLifecycleReport {
    throw new FrtArtifactStoreError("FRT_ARTIFACT_STORE_NOT_CONFIGURED");
  }
}

export class ContentAddressedFrtArtifactStore implements FrtArtifactStore {
  readonly configured = true;
  readonly #root: string;

  constructor(root: string) {
    const resolved = resolve(root);
    if (resolved === resolve("/")) throw new FrtArtifactStoreError("FRT_ARTIFACT_ROOT_UNSAFE");
    if (existsSync(resolved) && lstatSync(resolved).isSymbolicLink()) {
      throw new FrtArtifactStoreError("FRT_ARTIFACT_ROOT_SYMLINK_REJECTED");
    }
    mkdirSync(resolved, { recursive: true, mode: 0o700 });
    if (!lstatSync(resolved).isDirectory()) {
      throw new FrtArtifactStoreError("FRT_ARTIFACT_ROOT_UNSAFE");
    }
    this.#root = resolved;
  }

  #ensureOwnedDirectory(directory: string): void {
    const resolvedDirectory = resolve(directory);
    if (resolvedDirectory !== this.#root && !resolvedDirectory.startsWith(`${this.#root}${sep}`)) {
      throw new FrtArtifactStoreError("FRT_ARTIFACT_PATH_OUTSIDE_APPROVED_ROOT");
    }
    const relative = resolvedDirectory === this.#root
      ? []
      : resolvedDirectory.slice(this.#root.length + 1).split(sep);
    let current = this.#root;
    for (const component of relative) {
      current = resolve(current, component);
      if (!existsSync(current)) {
        mkdirSync(current, { mode: 0o700 });
        continue;
      }
      const metadata = lstatSync(current);
      if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
        throw new FrtArtifactStoreError("FRT_ARTIFACT_DIRECTORY_COMPONENT_UNSAFE");
      }
    }
  }

  #pathFor(digest: string): string {
    const hex = digest.slice("sha256:".length);
    return resolve(this.#root, "objects", hex.slice(0, 2), `${hex.slice(2)}.bin`);
  }

  put(name: string, bytes: Buffer): FrtRunnerArtifactReference {
    if (!artifactName.test(name)) throw new FrtArtifactStoreError("FRT_ARTIFACT_NAME_INVALID");
    if (!bytes.byteLength) throw new FrtArtifactStoreError("FRT_ARTIFACT_EMPTY");
    const digest = digestOf(bytes);
    const path = this.#pathFor(digest);
    if (!existsSync(path)) {
      this.#ensureOwnedDirectory(dirname(path));
      // Write to a temporary sibling and rename so a reader never sees a partial object.
      const temporary = `${path}.${randomUUID()}.tmp`;
      writeFileSync(temporary, bytes, { mode: 0o400 });
      renameSync(temporary, path);
    }
    return { name, uri: pathToFileURL(path).href, digest, byteCount: bytes.byteLength };
  }

  resolve(uri: string): Buffer {
    let path: string;
    try {
      const parsed = new URL(uri);
      if (parsed.protocol !== "file:") throw new FrtArtifactStoreError("FRT_ARTIFACT_URI_SCHEME_UNSUPPORTED");
      path = resolve(fileURLToPath(parsed));
    } catch (error) {
      if (error instanceof FrtArtifactStoreError) throw error;
      throw new FrtArtifactStoreError("FRT_ARTIFACT_URI_INVALID");
    }
    if (path !== this.#root && !path.startsWith(`${this.#root}${sep}`)) {
      throw new FrtArtifactStoreError("FRT_ARTIFACT_PATH_OUTSIDE_APPROVED_ROOT");
    }
    if (!existsSync(path) || !lstatSync(path).isFile()) {
      throw new FrtArtifactStoreError("FRT_ARTIFACT_NOT_FOUND");
    }
    const bytes = readFileSync(path);
    // The path is derived from the digest, so a mismatch means the object was tampered with.
    if (this.#pathFor(digestOf(bytes)) !== path) {
      throw new FrtArtifactStoreError("FRT_ARTIFACT_DIGEST_MISMATCH");
    }
    return bytes;
  }

  list(): readonly FrtStoredArtifact[] {
    const objectsRoot = resolve(this.#root, "objects");
    if (!existsSync(objectsRoot)) return [];
    this.#ensureOwnedDirectory(objectsRoot);
    const objects: FrtStoredArtifact[] = [];
    for (const prefixEntry of readdirSync(objectsRoot, { withFileTypes: true })) {
      if (!prefixEntry.isDirectory() || !/^[a-f0-9]{2}$/.test(prefixEntry.name)) continue;
      const prefixRoot = resolve(objectsRoot, prefixEntry.name);
      if (lstatSync(prefixRoot).isSymbolicLink()) {
        throw new FrtArtifactStoreError("FRT_ARTIFACT_OBJECT_SYMLINK_REJECTED");
      }
      for (const objectEntry of readdirSync(prefixRoot, { withFileTypes: true })) {
        if (!objectEntry.isFile() || !/^[a-f0-9]{62}\.bin$/.test(objectEntry.name)) continue;
        const path = resolve(prefixRoot, objectEntry.name);
        if (lstatSync(path).isSymbolicLink()) {
          throw new FrtArtifactStoreError("FRT_ARTIFACT_OBJECT_SYMLINK_REJECTED");
        }
        const hex = `${prefixEntry.name}${objectEntry.name.slice(0, -4)}`;
        const digest = `sha256:${hex}`;
        const metadata = statSync(path);
        objects.push({
          digest,
          uri: pathToFileURL(path).href,
          byteCount: metadata.size,
          modifiedAt: metadata.mtime.toISOString(),
        });
      }
    }
    return objects.sort((left, right) => left.digest.localeCompare(right.digest, "en-US"));
  }

  archiveGarbage(policy: FrtArtifactLifecyclePolicy): FrtArtifactLifecycleReport {
    const minimumAgeSeconds = policy.minimumAgeSeconds ?? 0;
    const retentionSeconds = policy.retentionSeconds;
    const maximumActiveBytes = policy.maximumActiveBytes;
    if (!Number.isFinite(minimumAgeSeconds) || minimumAgeSeconds < 0
        || (retentionSeconds !== undefined && (!Number.isFinite(retentionSeconds) || retentionSeconds < minimumAgeSeconds))
        || (maximumActiveBytes !== undefined && (!Number.isSafeInteger(maximumActiveBytes) || maximumActiveBytes < 0))) {
      throw new FrtArtifactStoreError("FRT_ARTIFACT_LIFECYCLE_POLICY_INVALID");
    }
    if (policy.liveDigests.some(item => !digestPattern.test(item))
        || new Set(policy.liveDigests).size !== policy.liveDigests.length) {
      throw new FrtArtifactStoreError("FRT_ARTIFACT_LIVE_DIGEST_SET_INVALID");
    }
    const now = policy.now ?? new Date();
    if (!Number.isFinite(now.getTime())) throw new FrtArtifactStoreError("FRT_ARTIFACT_LIFECYCLE_NOW_INVALID");
    const live = new Set(policy.liveDigests);
    const active = this.list();
    // Resolve every active object before lifecycle decisions so a tampered object is
    // reported as integrity failure instead of quietly archived out of sight.
    for (const object of active) this.resolve(object.uri);
    const beforeBytes = active.reduce((total, object) => total + object.byteCount, 0);
    const eligible = active
      .filter(object => !live.has(object.digest))
      .filter(object => now.getTime() - Date.parse(object.modifiedAt) >= minimumAgeSeconds * 1000)
      .sort((left, right) => Date.parse(left.modifiedAt) - Date.parse(right.modifiedAt)
        || left.digest.localeCompare(right.digest, "en-US"));
    const selected = new Set<string>();
    if (retentionSeconds !== undefined) {
      for (const object of eligible) {
        if (now.getTime() - Date.parse(object.modifiedAt) >= retentionSeconds * 1000) {
          selected.add(object.digest);
        }
      }
    }
    let projectedBytes = beforeBytes - eligible
      .filter(object => selected.has(object.digest))
      .reduce((total, object) => total + object.byteCount, 0);
    if (maximumActiveBytes !== undefined && projectedBytes > maximumActiveBytes) {
      for (const object of eligible) {
        if (projectedBytes <= maximumActiveBytes) break;
        if (selected.has(object.digest)) continue;
        selected.add(object.digest);
        projectedBytes -= object.byteCount;
      }
    }
    const toArchive = eligible.filter(object => selected.has(object.digest));
    const archived: FrtStoredArtifact[] = [];
    let recoveryRoot: string | null = null;
    if (toArchive.length > 0) {
      const archiveRoot = resolve(this.#root, "archive", `${now.toISOString().replaceAll(/[:.]/g, "-")}-${randomUUID()}`);
      this.#ensureOwnedDirectory(archiveRoot);
      recoveryRoot = pathToFileURL(archiveRoot).href;
      for (const object of toArchive) {
        const hex = object.digest.slice("sha256:".length);
        const destination = resolve(archiveRoot, hex.slice(0, 2), `${hex.slice(2)}.bin`);
        this.#ensureOwnedDirectory(dirname(destination));
        renameSync(fileURLToPath(object.uri), destination);
        archived.push({ ...object, uri: pathToFileURL(destination).href });
      }
    }
    const after = this.list();
    const afterBytes = after.reduce((total, object) => total + object.byteCount, 0);
    return {
      activeBytesBefore: beforeBytes,
      activeBytesAfter: afterBytes,
      activeObjectsBefore: active.length,
      activeObjectsAfter: after.length,
      archived,
      quotaSatisfied: maximumActiveBytes === undefined || afterBytes <= maximumActiveBytes,
      recoveryRoot,
    };
  }
}

export function frtArtifactStoreFromEnvironment(): FrtArtifactStore {
  const root = process.env.ELMOS_FRT_ARTIFACT_ROOT?.trim();
  return root ? new ContentAddressedFrtArtifactStore(root) : new DenyAllFrtArtifactStore();
}

export function isFrtArtifactDigest(value: string): boolean {
  return digestPattern.test(value);
}
