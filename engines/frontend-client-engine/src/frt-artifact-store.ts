import { createHash } from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  renameSync,
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
  readonly configured: boolean;
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
    this.#root = resolved;
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
      mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
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
}

export function frtArtifactStoreFromEnvironment(): FrtArtifactStore {
  const root = process.env.ELMOS_FRT_ARTIFACT_ROOT?.trim();
  return root ? new ContentAddressedFrtArtifactStore(root) : new DenyAllFrtArtifactStore();
}

export function isFrtArtifactDigest(value: string): boolean {
  return digestPattern.test(value);
}
