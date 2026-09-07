#!/usr/bin/env node
import {
  closeSync,
  constants,
  existsSync,
  fstatSync,
  linkSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, isAbsolute, resolve, sep } from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { pathToFileURL } from "node:url";
import { TextDecoder } from "node:util";

import { MiniappPackageContractError } from "./miniapp-package-contract.js";
import {
  materializeMiniappDeclaredOutputs,
  materializeMiniappCombinedOutputIndex,
  materializeMiniappGeneratedProjectArtifacts,
  type MiniappDeclaredOutputArtifact,
  type MiniappGeneratedProjectArtifact,
  type MiniappOutputArtifactIndexEntry,
  validateMiniappDeclaredOutputCatalog,
} from "./miniapp-output-contracts.js";
import {
  MINIAPP_SKILL_CATALOG,
  computeMiniappSourceFileSetDigest,
  handleMiniappSkillRequest,
  type MiniappConversionRun,
  type MiniappPackageConversionRun,
} from "./miniapp-skill-runtime.js";

const MAX_INPUT_BYTES = 32 * 1024 * 1024;

interface Options {
  readonly command: "run" | "package" | "digest" | "catalog";
  readonly input?: string;
  readonly output?: string;
  readonly materialize?: string;
}

function usage(): never {
  throw new Error("usage: miniapp [run|package|digest|catalog] [--input FILE] [--output FILE] [--materialize NEW_DIRECTORY_IN_PRIVATE_EXISTING_PARENT]");
}

function parseArgs(argv: readonly string[]): Options {
  let command: Options["command"] = "run";
  let cursor = 0;
  if (["run", "package", "digest", "catalog"].includes(argv[0] ?? "")) {
    command = argv[0] as Options["command"];
    cursor = 1;
  }
  let input: string | undefined;
  let output: string | undefined;
  let materialize: string | undefined;
  while (cursor < argv.length) {
    const option = argv[cursor++];
    const value = argv[cursor++];
    if (!value || value.startsWith("--")) usage();
    if (option === "--input" && input === undefined) input = value;
    else if (option === "--output" && output === undefined) output = value;
    else if (option === "--materialize" && materialize === undefined) materialize = value;
    else usage();
  }
  if (command !== "run" && command !== "package" && materialize !== undefined) usage();
  if (output !== undefined && materialize !== undefined) {
    throw new Error("--output cannot be combined with --materialize; materialized runs emit JSON on stdout");
  }
  return { command, ...(input === undefined ? {} : { input }), ...(output === undefined ? {} : { output }), ...(materialize === undefined ? {} : { materialize }) };
}

interface BoundedInputSnapshot {
  readonly text: string;
  readonly bytes: number;
}

function readBoundedInput(descriptor: number): BoundedInputSnapshot {
  const chunks: Buffer[] = [];
  const buffer = Buffer.allocUnsafe(64 * 1024);
  let bytes = 0;
  for (;;) {
    const count = readSync(descriptor, buffer, 0, buffer.byteLength, null);
    if (count === 0) break;
    bytes += count;
    if (bytes > MAX_INPUT_BYTES) throw new Error("input exceeds 32 MiB");
    chunks.push(Buffer.from(buffer.subarray(0, count)));
  }
  try {
    return {
      text: new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks, bytes)),
      bytes,
    };
  } catch {
    throw new Error("input must be valid UTF-8");
  }
}

function readInput(path: string | undefined): string {
  if (path === undefined) return readBoundedInput(0).text;
  const resolved = resolve(path);
  const pathIdentity = lstatSync(resolved);
  if (!pathIdentity.isFile() || pathIdentity.isSymbolicLink() || pathIdentity.size > MAX_INPUT_BYTES) {
    throw new Error("input must be a regular non-symlink file no larger than 32 MiB");
  }
  const descriptor = openSync(resolved, constants.O_RDONLY | noFollowFlag());
  try {
    const openIdentity = fstatSync(descriptor);
    if (!openIdentity.isFile()
      || openIdentity.dev !== pathIdentity.dev
      || openIdentity.ino !== pathIdentity.ino
      || openIdentity.size !== pathIdentity.size
      || openIdentity.mtimeMs !== pathIdentity.mtimeMs
      || openIdentity.ctimeMs !== pathIdentity.ctimeMs
      || openIdentity.size > MAX_INPUT_BYTES) {
      throw new Error("input file identity drifted before read");
    }
    const snapshot = readBoundedInput(descriptor);
    const finalOpenIdentity = fstatSync(descriptor);
    const finalPathIdentity = lstatSync(resolved);
    if (
      !finalOpenIdentity.isFile()
      || finalPathIdentity.isSymbolicLink()
      || !finalPathIdentity.isFile()
      || finalOpenIdentity.dev !== openIdentity.dev
      || finalOpenIdentity.ino !== openIdentity.ino
      || finalOpenIdentity.size !== openIdentity.size
      || finalOpenIdentity.mtimeMs !== openIdentity.mtimeMs
      || finalOpenIdentity.ctimeMs !== openIdentity.ctimeMs
      || finalPathIdentity.dev !== openIdentity.dev
      || finalPathIdentity.ino !== openIdentity.ino
      || finalPathIdentity.size !== openIdentity.size
      || finalPathIdentity.mtimeMs !== openIdentity.mtimeMs
      || finalPathIdentity.ctimeMs !== openIdentity.ctimeMs
      || snapshot.bytes !== openIdentity.size
      || Buffer.byteLength(snapshot.text, "utf8") !== snapshot.bytes
    ) {
      throw new Error("input file identity drifted during read");
    }
    return snapshot.text;
  } finally {
    closeSync(descriptor);
  }
}

function writeOutput(path: string | undefined, content: string): void {
  if (path === undefined) {
    process.stdout.write(content);
    return;
  }
  const resolved = resolve(path);
  if (existsSync(resolved)) throw new Error("output file must not already exist");
  mkdirSync(dirname(resolved), { recursive: true, mode: 0o755 });
  const temporary = `${resolved}.tmp-${process.pid}-${randomUUID()}`;
  let descriptor: number | undefined;
  let temporaryIdentity: { readonly dev: number; readonly ino: number } | undefined;
  let publishedIdentity: { readonly dev: number; readonly ino: number } | undefined;
  let completed = false;
  let primaryFailed = false;
  let primaryError: unknown;
  try {
    descriptor = openSync(temporary, "wx", 0o600);
    writeFileSync(descriptor, content, { encoding: "utf8" });
    const openIdentity = fstatSync(descriptor);
    const pathIdentity = lstatSync(temporary);
    if (
      !openIdentity.isFile()
      || pathIdentity.isSymbolicLink()
      || !pathIdentity.isFile()
      || openIdentity.dev !== pathIdentity.dev
      || openIdentity.ino !== pathIdentity.ino
      || openIdentity.size !== Buffer.byteLength(content, "utf8")
    ) {
      throw new Error("output staging file identity drifted");
    }
    temporaryIdentity = { dev: openIdentity.dev, ino: openIdentity.ino };
    linkSync(temporary, resolved);
    const outputIdentity = lstatSync(resolved);
    if (
      outputIdentity.isSymbolicLink()
      || !outputIdentity.isFile()
      || outputIdentity.dev !== openIdentity.dev
      || outputIdentity.ino !== openIdentity.ino
      || outputIdentity.size !== openIdentity.size
    ) {
      throw new Error("published output file identity drifted");
    }
    publishedIdentity = { dev: outputIdentity.dev, ino: outputIdentity.ino };
    completed = true;
  } catch (error) {
    primaryFailed = true;
    primaryError = error;
  }
  const cleanupErrors: unknown[] = [];
  if (descriptor !== undefined) {
    try {
      closeSync(descriptor);
    } catch (error) {
      cleanupErrors.push(error);
    }
  }
  if (temporaryIdentity !== undefined && existsSync(temporary)) {
    try {
      const current = lstatSync(temporary);
      if (
        !current.isSymbolicLink()
        && current.isFile()
        && current.dev === temporaryIdentity.dev
        && current.ino === temporaryIdentity.ino
      ) {
        unlinkSync(temporary);
      }
    } catch (error) {
      cleanupErrors.push(error);
    }
  }
  if (!completed && publishedIdentity !== undefined && existsSync(resolved)) {
    try {
      const current = lstatSync(resolved);
      if (
        !current.isSymbolicLink()
        && current.isFile()
        && current.dev === publishedIdentity.dev
        && current.ino === publishedIdentity.ino
      ) {
        unlinkSync(resolved);
      }
    } catch (error) {
      cleanupErrors.push(error);
    }
  }
  if (primaryFailed) {
    if (cleanupErrors.length > 0) {
      throw new AggregateError(
        [primaryError, ...cleanupErrors],
        primaryError instanceof Error ? primaryError.message : String(primaryError),
      );
    }
    throw primaryError;
  }
  if (cleanupErrors.length > 0) {
    const first = cleanupErrors[0];
    throw new AggregateError(
      cleanupErrors,
      first instanceof Error ? first.message : "output cleanup failed",
    );
  }
}

function safeArtifactPath(root: string, relative: string): string {
  if (isAbsolute(relative) || relative.includes("\\") || relative.split("/").some(segment => !segment || segment === "." || segment === "..")) {
    throw new Error(`generated artifact path is unsafe: ${relative}`);
  }
  const destination = resolve(root, relative);
  if (!destination.startsWith(`${root}${sep}`)) throw new Error(`generated artifact escapes output root: ${relative}`);
  return destination;
}

function lexicalPathExists(path: string): boolean {
  try {
    lstatSync(path);
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}

interface DirectoryReservation {
  readonly parentPath: string;
  readonly parentIdentity: DirectoryIdentity;
  readonly targetPath: string;
  readonly lockPath: string;
  readonly lockName: string;
  readonly descriptor: number;
}

interface DirectoryIdentity {
  readonly dev: number;
  readonly ino: number;
  readonly uid: number;
}

function sameDirectoryIdentity(
  actual: { readonly dev: number; readonly ino: number; readonly uid: number },
  expected: DirectoryIdentity,
): boolean {
  return actual.dev === expected.dev
    && actual.ino === expected.ino
    && actual.uid === expected.uid;
}

function captureOwnedDirectoryIdentity(path: string, label: string): DirectoryIdentity {
  const identity = lstatSync(path);
  if (
    identity.isSymbolicLink()
    || !identity.isDirectory()
    || (identity.mode & 0o077) !== 0
  ) {
    throw new Error(`${label} is not an owned directory`);
  }
  return { dev: identity.dev, ino: identity.ino, uid: identity.uid };
}

function assertOwnedDirectoryIdentity(
  path: string,
  expected: DirectoryIdentity,
  label: string,
): void {
  assertDirectoryIdentity(path, expected, label, true);
}

function assertDirectoryIdentity(
  path: string,
  expected: DirectoryIdentity,
  label: string,
  requirePrivate: boolean,
): void {
  const identity = lstatSync(path);
  if (
    identity.isSymbolicLink()
    || !identity.isDirectory()
    || (requirePrivate
      ? (identity.mode & 0o077) !== 0
      : (identity.mode & 0o022) !== 0)
    || identity.dev !== expected.dev
    || identity.ino !== expected.ino
    || identity.uid !== expected.uid
  ) {
    throw new Error(`${label} identity drifted`);
  }
}

function captureResolvedDirectoryIdentity(path: string, label: string): DirectoryIdentity {
  const previousPath = process.cwd();
  const previousIdentity = lstatSync(".");
  if (previousIdentity.isSymbolicLink() || !previousIdentity.isDirectory()) {
    throw new Error("current working directory is not a real directory");
  }
  process.chdir(path);
  try {
    const identity = lstatSync(".");
    if (identity.isSymbolicLink() || !identity.isDirectory()) {
      throw new Error(`${label} is not a directory`);
    }
    return { dev: identity.dev, ino: identity.ino, uid: identity.uid };
  } finally {
    process.chdir(previousPath);
    const restoredIdentity = lstatSync(".");
    if (
      restoredIdentity.isSymbolicLink()
      || !restoredIdentity.isDirectory()
      || !sameDirectoryIdentity(restoredIdentity, previousIdentity)
    ) {
      throw new Error("current working directory identity drifted during materialization");
    }
  }
}

function ownedDirectoryHasIdentity(path: string, expected: DirectoryIdentity): boolean {
  try {
    const identity = lstatSync(path);
    return !identity.isSymbolicLink()
      && identity.isDirectory()
      && (identity.mode & 0o077) === 0
      && identity.dev === expected.dev
      && identity.ino === expected.ino
      && identity.uid === expected.uid;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}

function withOwnedWorkingDirectory<T>(
  path: string,
  expected: DirectoryIdentity,
  label: string,
  operation: () => T,
): T {
  return withVerifiedWorkingDirectory(path, expected, label, true, operation);
}

function withVerifiedWorkingDirectory<T>(
  path: string,
  expected: DirectoryIdentity,
  label: string,
  requirePrivate: boolean,
  operation: () => T,
): T {
  const previousPath = process.cwd();
  const previousIdentity = lstatSync(".");
  if (previousIdentity.isSymbolicLink() || !previousIdentity.isDirectory()) {
    throw new Error("current working directory is not a real directory");
  }
  process.chdir(path);
  try {
    assertDirectoryIdentity(".", expected, label, requirePrivate);
    return operation();
  } finally {
    process.chdir(previousPath);
    const restoredIdentity = lstatSync(".");
    if (
      restoredIdentity.isSymbolicLink()
      || !restoredIdentity.isDirectory()
      || !sameDirectoryIdentity(restoredIdentity, previousIdentity)
    ) {
      throw new Error("current working directory identity drifted during materialization");
    }
  }
}

function reserveMaterializeTarget(root: string): DirectoryReservation {
  const requestedParentPath = dirname(root);
  if (!lexicalPathExists(requestedParentPath)) {
    throw new Error("materialize parent directory must already exist");
  }
  const parentPath = realpathSync(requestedParentPath);
  const parentPathIdentity = lstatSync(parentPath);
  const currentUid = typeof process.getuid === "function" ? process.getuid() : undefined;
  if (
    parentPathIdentity.isSymbolicLink()
    || !parentPathIdentity.isDirectory()
    || (parentPathIdentity.mode & 0o022) !== 0
    || (currentUid !== undefined && parentPathIdentity.uid !== currentUid)
  ) {
    throw new Error("materialize parent directory must be owned by the current user and not group/world writable");
  }
  const parentIdentity = captureResolvedDirectoryIdentity(parentPath, "materialize parent directory");
  const targetPath = resolve(parentPath, basename(root));
  const lockName = `${basename(targetPath)}.elmos-miniapp-materialize.lock`;
  const lockPath = `${targetPath}.elmos-miniapp-materialize.lock`;
  let opened: number | undefined;
  let openedIdentity: DirectoryIdentity | undefined;
  try {
    const descriptor = withVerifiedWorkingDirectory(
      parentPath,
      parentIdentity,
      "materialize parent directory",
      false,
      () => {
        let descriptor: number;
        try {
          descriptor = openSync(
            lockName,
            constants.O_CREAT | constants.O_EXCL | constants.O_RDWR | noFollowFlag(),
            0o600,
          );
          opened = descriptor;
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code === "EEXIST") {
            throw new Error("materialize target is reserved by another writer");
          }
          throw error;
        }
        const openIdentity = fstatSync(descriptor);
        openedIdentity = { dev: openIdentity.dev, ino: openIdentity.ino, uid: openIdentity.uid };
        const pathIdentity = lstatSync(lockName);
        if (
          !openIdentity.isFile()
          || pathIdentity.isSymbolicLink()
          || !pathIdentity.isFile()
          || !sameDirectoryIdentity(pathIdentity, openIdentity)
        ) {
          throw new Error("materialize reservation is not a regular owned file");
        }
        return descriptor;
      },
    );
    return { parentPath, parentIdentity, targetPath, lockPath, lockName, descriptor };
  } catch (error) {
    const cleanupErrors: unknown[] = [];
    try {
      if (openedIdentity !== undefined) {
        try {
          const pathIdentity = lstatSync(lockPath);
          if (
            !pathIdentity.isSymbolicLink()
            && pathIdentity.isFile()
            && sameDirectoryIdentity(pathIdentity, openedIdentity)
          ) {
            unlinkSync(lockPath);
          }
        } catch (cleanupError) {
          if ((cleanupError as NodeJS.ErrnoException).code !== "ENOENT") {
            cleanupErrors.push(cleanupError);
          }
        }
      }
    } finally {
      if (opened !== undefined) {
        try {
          closeSync(opened);
        } catch (cleanupError) {
          cleanupErrors.push(cleanupError);
        }
      }
    }
    if (cleanupErrors.length > 0) {
      throw new AggregateError(
        [error, ...cleanupErrors],
        "materialize reservation acquisition and cleanup failed",
      );
    }
    throw error;
  }
}

function releaseMaterializeTarget(reservation: DirectoryReservation): void {
  let releaseFailed = false;
  let releaseError: unknown;
  try {
    withVerifiedWorkingDirectory(
      reservation.parentPath,
      reservation.parentIdentity,
      "materialize parent directory during reservation release",
      false,
      () => {
        const openIdentity = fstatSync(reservation.descriptor);
        const pathIdentity = lstatSync(reservation.lockName);
        if (pathIdentity.isSymbolicLink()
          || !pathIdentity.isFile()
          || pathIdentity.dev !== openIdentity.dev
          || pathIdentity.ino !== openIdentity.ino) {
          throw new Error("materialize reservation identity drifted");
        }
        unlinkSync(reservation.lockName);
      },
    );
  } catch (error) {
    releaseFailed = true;
    releaseError = error;
  }
  try {
    closeSync(reservation.descriptor);
  } catch (error) {
    if (releaseFailed) {
      throw new AggregateError(
        [releaseError, error],
        "materialize reservation release and descriptor close failed",
      );
    }
    throw error;
  }
  if (releaseFailed) throw releaseError;
}

function assertMaterializeReservation(reservation: DirectoryReservation, phase: string): void {
  withVerifiedWorkingDirectory(
    reservation.parentPath,
    reservation.parentIdentity,
    `materialize parent directory ${phase}`,
    false,
    () => {
      const openIdentity = fstatSync(reservation.descriptor);
      const pathIdentity = lstatSync(reservation.lockName);
      if (
        !openIdentity.isFile()
        || pathIdentity.isSymbolicLink()
        || !pathIdentity.isFile()
        || !sameDirectoryIdentity(pathIdentity, openIdentity)
      ) {
        throw new Error(`materialize reservation identity drifted ${phase}`);
      }
    },
  );
}

function sha256(content: string): string {
  return `sha256:${createHash("sha256").update(content, "utf8").digest("hex")}`;
}

function canonicalIdentity(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalIdentity).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value as Readonly<Record<string, unknown>>)
      .sort()
      .map(key => `${JSON.stringify(key)}:${canonicalIdentity((value as Readonly<Record<string, unknown>>)[key])}`)
      .join(",")}}`;
  }
  const primitive = JSON.stringify(value);
  if (primitive === undefined) throw new Error("materialize identity contains an unsupported value");
  return primitive;
}

interface VerifiedTextArtifact {
  readonly materializedPath: string;
  readonly content: string;
  readonly digest: string;
  readonly bytes: number;
  readonly label: string;
}

interface VerifiedArtifactIdentity {
  readonly dev: number;
  readonly ino: number;
  readonly bytes: number;
}

interface MaterializedArtifactLocation {
  readonly directory: string;
  readonly directoryRelative: string;
  readonly name: string;
}

function noFollowFlag(): number {
  const flag: unknown = constants.O_NOFOLLOW;
  if (typeof flag !== "number" || flag === 0) {
    throw new Error("materialization requires filesystem O_NOFOLLOW support");
  }
  return flag;
}

function materializedArtifactLocation(
  root: string,
  materializedPath: string,
): MaterializedArtifactLocation {
  safeArtifactPath(root, materializedPath);
  const segments = materializedPath.split("/");
  const name = segments.pop();
  if (name === undefined || name !== basename(name)) {
    throw new Error(`generated artifact basename is unsafe: ${materializedPath}`);
  }
  const directoryRelative = segments.join("/");
  return {
    directory: directoryRelative.length === 0
      ? root
      : safeArtifactPath(root, directoryRelative),
    directoryRelative,
    name,
  };
}

function materializedDirectoryPaths(
  root: string,
  artifacts: readonly VerifiedTextArtifact[],
): readonly string[] {
  const files = new Set<string>();
  const directories = new Set<string>();
  for (const artifact of artifacts) {
    safeArtifactPath(root, artifact.materializedPath);
    if (files.has(artifact.materializedPath)) {
      throw new Error(`materialized artifact path conflicts: ${artifact.materializedPath}`);
    }
    files.add(artifact.materializedPath);
    const segments = artifact.materializedPath.split("/");
    for (let length = 1; length < segments.length; length += 1) {
      directories.add(segments.slice(0, length).join("/"));
    }
  }
  for (const directory of directories) {
    if (files.has(directory)) {
      throw new Error(`materialized file and directory paths conflict: ${directory}`);
    }
  }
  return [...directories].sort((left, right) => {
    const depth = left.split("/").length - right.split("/").length;
    return depth === 0 ? left.localeCompare(right) : depth;
  });
}

function createVerifiedMaterializedDirectories(
  root: string,
  rootIdentity: DirectoryIdentity,
  artifacts: readonly VerifiedTextArtifact[],
): ReadonlyMap<string, DirectoryIdentity> {
  const identities = new Map<string, DirectoryIdentity>([["", rootIdentity]]);
  withOwnedWorkingDirectory(root, rootIdentity, "materialize staging directory", () => {
    if (readdirSync(".").length !== 0) {
      throw new Error("materialize staging directory was not empty before directory creation");
    }
  });
  for (const relative of materializedDirectoryPaths(root, artifacts)) {
    const segments = relative.split("/");
    const name = segments.pop();
    if (name === undefined || name !== basename(name)) {
      throw new Error(`materialized directory basename is unsafe: ${relative}`);
    }
    const parentRelative = segments.join("/");
    const parentIdentity = identities.get(parentRelative);
    if (parentIdentity === undefined) {
      throw new Error(`materialized directory parent is missing: ${relative}`);
    }
    const parentPath = parentRelative.length === 0
      ? root
      : safeArtifactPath(root, parentRelative);
    const identity = withOwnedWorkingDirectory(
      parentPath,
      parentIdentity,
      `materialize directory parent ${parentRelative || "."}`,
      () => {
        if (lexicalPathExists(name)) {
          throw new Error(`materialized directory appeared before creation: ${relative}`);
        }
        mkdirSync(name, { recursive: false, mode: 0o700 });
        return captureOwnedDirectoryIdentity(name, `materialized directory ${relative}`);
      },
    );
    identities.set(relative, identity);
  }
  return identities;
}

function readExactDescriptorBytes(descriptor: number, expectedBytes: number): Buffer {
  const content = Buffer.alloc(expectedBytes);
  let offset = 0;
  while (offset < expectedBytes) {
    const count = readSync(descriptor, content, offset, expectedBytes - offset, offset);
    if (count === 0) throw new Error("materialized artifact ended before its declared byte count");
    offset += count;
  }
  const extra = Buffer.alloc(1);
  if (readSync(descriptor, extra, 0, 1, expectedBytes) !== 0) {
    throw new Error("materialized artifact exceeded its declared byte count");
  }
  return content;
}

function writeVerifiedTextArtifact(
  staging: string,
  directoryIdentities: ReadonlyMap<string, DirectoryIdentity>,
  writtenPaths: Set<string>,
  artifact: VerifiedTextArtifact,
): void {
  if (writtenPaths.has(artifact.materializedPath)) {
    throw new Error(`materialized artifact path conflicts: ${artifact.materializedPath}`);
  }
  const expectedBytes = Buffer.byteLength(artifact.content, "utf8");
  const expectedDigest = sha256(artifact.content);
  if (artifact.bytes !== expectedBytes || artifact.digest !== expectedDigest) {
    throw new Error(`${artifact.label} identity mismatch before write: ${artifact.materializedPath}`);
  }
  const location = materializedArtifactLocation(staging, artifact.materializedPath);
  const directoryIdentity = directoryIdentities.get(location.directoryRelative);
  if (directoryIdentity === undefined) {
    throw new Error(`materialized artifact parent identity is missing: ${artifact.materializedPath}`);
  }
  withOwnedWorkingDirectory(
    location.directory,
    directoryIdentity,
    `materialize artifact parent ${location.directoryRelative || "."}`,
    () => {
      let descriptor: number | undefined;
      try {
        descriptor = openSync(
          location.name,
          constants.O_CREAT | constants.O_EXCL | constants.O_RDWR | noFollowFlag(),
          0o644,
        );
        writeFileSync(descriptor, artifact.content, { encoding: "utf8" });
        const openIdentity = fstatSync(descriptor);
        const pathIdentity = lstatSync(location.name);
        if (
          !openIdentity.isFile()
          || pathIdentity.isSymbolicLink()
          || !pathIdentity.isFile()
          || openIdentity.dev !== pathIdentity.dev
          || openIdentity.ino !== pathIdentity.ino
          || openIdentity.size !== artifact.bytes
          || pathIdentity.size !== artifact.bytes
        ) {
          throw new Error(`${artifact.label} identity mismatch after write: ${artifact.materializedPath}`);
        }
        const written = readExactDescriptorBytes(descriptor, artifact.bytes);
        if (!written.equals(Buffer.from(artifact.content, "utf8"))
          || sha256(written.toString("utf8")) !== artifact.digest) {
          throw new Error(`${artifact.label} identity mismatch after write: ${artifact.materializedPath}`);
        }
        const finalPathIdentity = lstatSync(location.name);
        if (
          finalPathIdentity.isSymbolicLink()
          || !finalPathIdentity.isFile()
          || finalPathIdentity.dev !== openIdentity.dev
          || finalPathIdentity.ino !== openIdentity.ino
          || finalPathIdentity.size !== artifact.bytes
        ) {
          throw new Error(`${artifact.label} identity mismatch after write: ${artifact.materializedPath}`);
        }
      } finally {
        if (descriptor !== undefined) closeSync(descriptor);
      }
    },
  );
  writtenPaths.add(artifact.materializedPath);
}

function assertExactStagingInventory(
  directory: string,
  writtenPaths: ReadonlySet<string>,
  directoryIdentities: ReadonlyMap<string, DirectoryIdentity>,
): void {
  const actualFiles = new Set<string>();
  const actualDirectories = new Set<string>([""]);
  const orderedDirectories = [...directoryIdentities.entries()].sort(([left], [right]) => {
    const depth = left.split("/").length - right.split("/").length;
    return depth === 0 ? left.localeCompare(right) : depth;
  });
  for (const [relative, expectedIdentity] of orderedDirectories) {
    const path = relative.length === 0 ? directory : safeArtifactPath(directory, relative);
    withOwnedWorkingDirectory(path, expectedIdentity, `materialize inventory directory ${relative || "."}`, () => {
      for (const entry of readdirSync(".", { withFileTypes: true })) {
        const childRelative = relative.length === 0 ? entry.name : `${relative}/${entry.name}`;
        const identity = lstatSync(entry.name);
        if (identity.isSymbolicLink()) {
          throw new Error(`materialize staging contains an unsafe entry: ${childRelative}`);
        }
        if (identity.isDirectory()) {
          const expectedChild = directoryIdentities.get(childRelative);
          if (
            expectedChild === undefined
            || (identity.mode & 0o077) !== 0
            || !sameDirectoryIdentity(identity, expectedChild)
          ) {
            throw new Error(`materialize staging directory identity drifted: ${childRelative}`);
          }
          actualDirectories.add(childRelative);
        } else if (identity.isFile()) {
          if (!writtenPaths.has(childRelative)) {
            throw new Error(`materialize staging contains an unowned file: ${childRelative}`);
          }
          actualFiles.add(childRelative);
        } else {
          throw new Error(`materialize staging contains an unsafe entry: ${childRelative}`);
        }
      }
    });
  }
  const expectedFiles = [...writtenPaths].sort();
  const observedFiles = [...actualFiles].sort();
  const expectedDirectories = [...directoryIdentities.keys()].sort();
  const observedDirectories = [...actualDirectories].sort();
  if (
    observedFiles.length !== expectedFiles.length
    || observedFiles.some((path, index) => path !== expectedFiles[index])
    || observedDirectories.length !== expectedDirectories.length
    || observedDirectories.some((path, index) => path !== expectedDirectories[index])
  ) {
    throw new Error(
      `materialize staging inventory mismatch: expected=${expectedFiles.length} actual=${observedFiles.length}`,
    );
  }
}

function assertVerifiedMaterializedContents(
  directory: string,
  artifacts: readonly VerifiedTextArtifact[],
  phase: "before commit" | "after publish",
  directoryIdentities: ReadonlyMap<string, DirectoryIdentity>,
  expectedIdentities?: ReadonlyMap<string, VerifiedArtifactIdentity>,
): ReadonlyMap<string, VerifiedArtifactIdentity> {
  const identities = new Map<string, VerifiedArtifactIdentity>();
  for (const artifact of artifacts) {
    const location = materializedArtifactLocation(directory, artifact.materializedPath);
    const directoryIdentity = directoryIdentities.get(location.directoryRelative);
    if (directoryIdentity === undefined) {
      throw new Error(`materialize artifact parent identity is missing: ${artifact.materializedPath}`);
    }
    const identity = withOwnedWorkingDirectory(
      location.directory,
      directoryIdentity,
      `materialize verification parent ${location.directoryRelative || "."}`,
      () => {
        const pathIdentity = lstatSync(location.name);
        if (pathIdentity.isSymbolicLink() || !pathIdentity.isFile() || pathIdentity.size !== artifact.bytes) {
          throw new Error(`materialize artifact identity drifted ${phase}: ${artifact.materializedPath}`);
        }
        const descriptor = openSync(location.name, constants.O_RDONLY | noFollowFlag());
        try {
          const openIdentity = fstatSync(descriptor);
          const expectedIdentity = expectedIdentities?.get(artifact.materializedPath);
          if (!openIdentity.isFile()
            || openIdentity.dev !== pathIdentity.dev
            || openIdentity.ino !== pathIdentity.ino
            || openIdentity.size !== artifact.bytes
            || (expectedIdentity !== undefined && (
              openIdentity.dev !== expectedIdentity.dev
              || openIdentity.ino !== expectedIdentity.ino
              || openIdentity.size !== expectedIdentity.bytes
            ))) {
            throw new Error(`materialize artifact identity drifted ${phase}: ${artifact.materializedPath}`);
          }
          const content = readExactDescriptorBytes(descriptor, artifact.bytes);
          const finalPathIdentity = lstatSync(location.name);
          if (finalPathIdentity.isSymbolicLink()
            || !finalPathIdentity.isFile()
            || finalPathIdentity.dev !== openIdentity.dev
            || finalPathIdentity.ino !== openIdentity.ino
            || finalPathIdentity.size !== artifact.bytes
            || !content.equals(Buffer.from(artifact.content, "utf8"))
            || sha256(content.toString("utf8")) !== artifact.digest) {
            throw new Error(`materialize artifact identity drifted ${phase}: ${artifact.materializedPath}`);
          }
          return {
            dev: openIdentity.dev,
            ino: openIdentity.ino,
            bytes: openIdentity.size,
          };
        } finally {
          closeSync(descriptor);
        }
      },
    );
    identities.set(artifact.materializedPath, identity);
  }
  return identities;
}

function assertExactObjectKeys(
  value: unknown,
  expected: readonly string[],
  label: string,
): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const actual = Object.keys(value).sort();
  const required = [...expected].sort();
  if (actual.length !== required.length
    || actual.some((key, index) => key !== required[index])) {
    throw new Error(`${label} keys drifted`);
  }
}

function assertGeneratedProjectIndexClosure(
  candidates: readonly MiniappGeneratedProjectArtifact[],
  declared: readonly MiniappDeclaredOutputArtifact[],
): void {
  const groups = new Map<string, MiniappGeneratedProjectArtifact[]>();
  for (const candidate of candidates) {
    const key = `${candidate.ownerSkill}\u0000${candidate.declaredPattern}`;
    const group = groups.get(key) ?? [];
    group.push(candidate);
    groups.set(key, group);
  }
  const wildcardIndexes = declared.filter(artifact => artifact.declaredPattern.endsWith("/**"));
  for (const index of wildcardIndexes) {
    const key = `${index.ownerSkill}\u0000${index.declaredPattern}`;
    const group = groups.get(key) ?? [];
    if (index.state === "PASSED_LOCAL" && group.length === 0) {
      throw new Error(`locally passed wildcard output has no generated files: ${index.ownerSkill}`);
    }
    if (index.state !== "PASSED_LOCAL" && group.length > 0) {
      throw new Error(`non-passing wildcard output has generated files: ${index.ownerSkill}`);
    }
    if (group.length === 0) continue;
    const [first] = group;
    if (first === undefined) throw new Error(`unreachable empty generated project group: ${key}`);
    if (index.materializedPath !== `${first.declaredBasePath}/project-index.json`) {
      throw new Error(`generated project index path mismatch: ${index.ownerSkill}`);
    }
    const expectedFiles = [...group]
      .sort((left, right) => left.sourcePath < right.sourcePath ? -1 : left.sourcePath > right.sourcePath ? 1 : 0)
      .map(candidate => {
        if (candidate.declaredBasePath !== first.declaredBasePath
          || candidate.materializedPath !== `${candidate.declaredBasePath}/${candidate.sourcePath}`) {
          throw new Error(`generated project candidate path mismatch: ${candidate.materializedPath}`);
        }
        return {
          bytes: candidate.bytes,
          path: candidate.materializedPath,
          sha256: candidate.digest.slice("sha256:".length),
          source_path: candidate.sourcePath,
        };
      });
    let body: unknown;
    try {
      body = JSON.parse(index.content);
    } catch {
      throw new Error(`generated project index is not valid JSON: ${index.materializedPath}`);
    }
    assertExactObjectKeys(body, [
      "declared_base_path",
      "declared_pattern",
      "exact_declared_files_materialized",
      "files",
      "owner_skill",
      "platform",
      "project_status",
      "schema_version",
      "static_validation",
    ], `generated project index ${index.ownerSkill}`);
    if (body.schema_version !== "1.0.0"
      || body.platform !== first.platform
      || body.owner_skill !== first.ownerSkill
      || body.declared_pattern !== first.declaredPattern
      || body.declared_base_path !== first.declaredBasePath
      || body.project_status !== "GENERATED"
      || body.static_validation !== "PASSED"
      || body.exact_declared_files_materialized !== true
      || JSON.stringify(body.files) !== JSON.stringify(expectedFiles)) {
      throw new Error(`generated project index identity closure mismatch: ${index.ownerSkill}`);
    }
    groups.delete(key);
  }
  if (groups.size > 0) {
    throw new Error(`generated project files lack a declared wildcard index: ${[...groups.keys()].join(",")}`);
  }
}

function declaredGlobalIndexes(
  declared: readonly MiniappDeclaredOutputArtifact[],
): readonly MiniappDeclaredOutputArtifact[] {
  const indexes = declared.filter(artifact =>
    artifact.declaredPattern === "runs/<run-id>/artifacts-index.json"
    || artifact.declaredPattern === "artifact-index.json");
  if (indexes.length !== 2) {
    throw new Error(`global artifact index count mismatch: expected=2 actual=${indexes.length}`);
  }
  return indexes;
}

function assertGlobalOutputIndexClosure(
  run: MiniappConversionRun | MiniappPackageConversionRun,
  declared: readonly MiniappDeclaredOutputArtifact[],
  combined: readonly MiniappOutputArtifactIndexEntry[],
): readonly string[] {
  const indexes = declaredGlobalIndexes(declared);
  const selfIndexPaths = indexes.map(index => index.materializedPath);
  for (const index of indexes) {
    let body: unknown;
    try {
      body = JSON.parse(index.content);
    } catch {
      throw new Error(`global artifact index is not valid JSON: ${index.materializedPath}`);
    }
    assertExactObjectKeys(body, [
      "artifacts",
      "run_id",
      "schema_version",
      "self_referential_outputs_excluded",
    ], `global artifact index ${index.ownerSkill}`);
    if (body.run_id !== run.runId
      || body.schema_version !== "1.0.0"
      || canonicalIdentity(body.artifacts) !== canonicalIdentity(combined)
      || JSON.stringify(body.self_referential_outputs_excluded) !== JSON.stringify(selfIndexPaths)) {
      throw new Error(`global artifact index identity closure mismatch: ${index.ownerSkill}`);
    }
  }
  return selfIndexPaths;
}

function assertIndexedStagingClosure(
  writtenPaths: ReadonlySet<string>,
  combined: readonly MiniappOutputArtifactIndexEntry[],
  selfIndexPaths: readonly string[],
): void {
  const indexedPaths = combined.map(entry => entry.materialized_path);
  const expected = new Set([
    ...indexedPaths,
    ...selfIndexPaths,
  ]);
  const caseInsensitive = new Set([...expected].map(path => path.normalize("NFC").toLowerCase()));
  if (expected.size !== indexedPaths.length + selfIndexPaths.length
    || caseInsensitive.size !== expected.size
    || expected.size !== writtenPaths.size
    || [...expected].some(path => !writtenPaths.has(path))) {
    throw new Error(
      `materialize indexed inventory mismatch: indexed=${indexedPaths.length} selfIndexes=${selfIndexPaths.length} written=${writtenPaths.size}`,
    );
  }
}

function writeDeclaredOutputs(
  staging: string,
  directoryIdentities: ReadonlyMap<string, DirectoryIdentity>,
  writtenPaths: Set<string>,
  artifacts: readonly MiniappDeclaredOutputArtifact[],
  beforeWrite?: (artifactPath: string) => void,
): void {
  const expectedCount = validateMiniappDeclaredOutputCatalog().requiredOutputs;
  if (artifacts.length !== expectedCount) {
    throw new Error(`declared output count mismatch: expected=${expectedCount} actual=${artifacts.length}`);
  }
  for (const artifact of artifacts) {
    beforeWrite?.(artifact.materializedPath);
    writeVerifiedTextArtifact(staging, directoryIdentities, writtenPaths, {
      ...artifact,
      label: "declared output",
    });
  }
}

export interface MiniappMaterializeHooks {
  readonly beforeArtifactWrite?: (context: {
    readonly root: string;
    readonly staging: string;
    readonly artifactPath: string;
  }) => void;
  readonly beforeCommit?: (context: {
    readonly root: string;
    readonly staging: string;
  }) => void;
  readonly beforePublish?: (context: {
    readonly root: string;
    readonly staging: string;
  }) => void;
  readonly afterPublish?: (context: {
    readonly root: string;
    readonly staging: string;
  }) => void;
}

export function materializeMiniappRun(
  run: MiniappConversionRun | MiniappPackageConversionRun,
  path: string,
  hooks: MiniappMaterializeHooks = {},
): void {
  const requestedRoot = resolve(path);
  if (dirname(requestedRoot) === requestedRoot) {
    throw new Error("materialize target must not be a filesystem root");
  }
  if (lexicalPathExists(requestedRoot)) {
    throw new Error("materialize target must not already exist");
  }
  const reservation = reserveMaterializeTarget(requestedRoot);
  const root = reservation.targetPath;
  const rootName = basename(root);
  const stagingName = `${rootName}.tmp-${process.pid}-${randomUUID()}`;
  const staging = resolve(reservation.parentPath, stagingName);
  let stagingIdentity: DirectoryIdentity | undefined;
  let publishedIdentity: DirectoryIdentity | undefined;
  let primaryFailed = false;
  let primaryError: unknown;
  try {
    stagingIdentity = withVerifiedWorkingDirectory(
      reservation.parentPath,
      reservation.parentIdentity,
      "materialize parent directory during staging creation",
      false,
      () => {
        if (lexicalPathExists(rootName)) throw new Error("materialize target must not already exist");
        if (lexicalPathExists(stagingName)) throw new Error("materialize staging path already exists");
        mkdirSync(stagingName, { recursive: false, mode: 0o700 });
        return captureOwnedDirectoryIdentity(stagingName, "materialize staging directory");
      },
    );
    assertMaterializeReservation(reservation, "after staging creation");
    const writtenPaths = new Set<string>();
    const candidates = materializeMiniappGeneratedProjectArtifacts(run);
    const declared = materializeMiniappDeclaredOutputs(run);
    const combinedIndex = materializeMiniappCombinedOutputIndex(run);
    assertGeneratedProjectIndexClosure(candidates, declared);
    const selfIndexPaths = assertGlobalOutputIndexClosure(run, declared, combinedIndex);
    const verifiedArtifacts = [
      ...candidates.map(candidate => ({ ...candidate, label: `generated ${candidate.platform} project` })),
      ...declared.map(artifact => ({ ...artifact, label: "declared output" })),
    ];
    const directoryIdentities = createVerifiedMaterializedDirectories(
      staging,
      stagingIdentity,
      verifiedArtifacts,
    );
    for (const candidate of candidates) {
      hooks.beforeArtifactWrite?.({
        root,
        staging,
        artifactPath: candidate.materializedPath,
      });
      assertMaterializeReservation(reservation, "before artifact write");
      writeVerifiedTextArtifact(staging, directoryIdentities, writtenPaths, {
        ...candidate,
        label: `generated ${candidate.platform} project`,
      });
    }
    writeDeclaredOutputs(
      staging,
      directoryIdentities,
      writtenPaths,
      declared,
      artifactPath => {
        hooks.beforeArtifactWrite?.({
          root,
          staging,
          artifactPath,
        });
        assertMaterializeReservation(reservation, "before artifact write");
      },
    );
    assertIndexedStagingClosure(writtenPaths, combinedIndex, selfIndexPaths);
    assertOwnedDirectoryIdentity(staging, stagingIdentity, "materialize staging directory");
    assertExactStagingInventory(staging, writtenPaths, directoryIdentities);
    hooks.beforeCommit?.({ root, staging });
    assertMaterializeReservation(reservation, "after beforeCommit hook");
    assertOwnedDirectoryIdentity(staging, stagingIdentity, "materialize staging directory");
    assertExactStagingInventory(staging, writtenPaths, directoryIdentities);
    const verifiedIdentities = assertVerifiedMaterializedContents(
      staging,
      verifiedArtifacts,
      "before commit",
      directoryIdentities,
    );
    assertOwnedDirectoryIdentity(staging, stagingIdentity, "materialize staging directory");
    withVerifiedWorkingDirectory(
      reservation.parentPath,
      reservation.parentIdentity,
      "materialize parent directory during target check",
      false,
      () => {
        if (lexicalPathExists(rootName)) throw new Error("materialize target appeared during staging");
      },
    );
    hooks.beforePublish?.({ root, staging });
    assertMaterializeReservation(reservation, "after beforePublish hook");
    assertOwnedDirectoryIdentity(staging, stagingIdentity, "materialize staging directory before publish");
    assertExactStagingInventory(staging, writtenPaths, directoryIdentities);
    assertVerifiedMaterializedContents(
      staging,
      verifiedArtifacts,
      "before commit",
      directoryIdentities,
      verifiedIdentities,
    );
    const stagingIdentityBeforePublish = stagingIdentity;
    withVerifiedWorkingDirectory(
      reservation.parentPath,
      reservation.parentIdentity,
      "materialize parent directory during publish",
      false,
      () => {
        assertOwnedDirectoryIdentity(
          stagingName,
          stagingIdentityBeforePublish,
          "materialize staging directory before rename",
        );
        if (lexicalPathExists(rootName)) throw new Error("materialize target appeared before publish");
        renameSync(stagingName, rootName);
        assertOwnedDirectoryIdentity(
          rootName,
          stagingIdentityBeforePublish,
          "materialize published directory after rename",
        );
      },
    );
    publishedIdentity = stagingIdentityBeforePublish;
    assertOwnedDirectoryIdentity(root, publishedIdentity, "materialize published directory");
    assertExactStagingInventory(root, writtenPaths, directoryIdentities);
    assertVerifiedMaterializedContents(
      root,
      verifiedArtifacts,
      "after publish",
      directoryIdentities,
      verifiedIdentities,
    );
    hooks.afterPublish?.({ root, staging });
    assertMaterializeReservation(reservation, "after afterPublish hook");
    assertOwnedDirectoryIdentity(root, publishedIdentity, "materialize published directory");
    assertExactStagingInventory(root, writtenPaths, directoryIdentities);
    assertVerifiedMaterializedContents(
      root,
      verifiedArtifacts,
      "after publish",
      directoryIdentities,
      verifiedIdentities,
    );
    assertMaterializeReservation(reservation, "before completion");
  } catch (error) {
    primaryFailed = true;
    primaryError = error;
  }
  const cleanupErrors: unknown[] = [];
  try {
    if (stagingIdentity !== undefined) {
      const cleanupStagingIdentity = stagingIdentity;
      withVerifiedWorkingDirectory(
        reservation.parentPath,
        reservation.parentIdentity,
        "materialize parent directory during staging cleanup",
        false,
        () => {
          if (ownedDirectoryHasIdentity(stagingName, cleanupStagingIdentity)) {
            rmSync(stagingName, { recursive: true });
          }
        },
      );
    }
  } catch (error) {
    cleanupErrors.push(error);
  }
  const cleanupPublishedOutput = (): void => {
    if (publishedIdentity === undefined) return;
    const cleanupPublishedIdentity = publishedIdentity;
    withVerifiedWorkingDirectory(
      reservation.parentPath,
      reservation.parentIdentity,
      "materialize parent directory during publication cleanup",
      false,
      () => {
        if (ownedDirectoryHasIdentity(rootName, cleanupPublishedIdentity)) {
          rmSync(rootName, { recursive: true });
        }
      },
    );
  };
  try {
    if (primaryFailed) cleanupPublishedOutput();
  } catch (error) {
    cleanupErrors.push(error);
  }
  let reservationReleased = false;
  try {
    releaseMaterializeTarget(reservation);
    reservationReleased = true;
  } catch (error) {
    cleanupErrors.push(error);
  }
  if (!primaryFailed && !reservationReleased) {
    try {
      cleanupPublishedOutput();
    } catch (error) {
      cleanupErrors.push(error);
    }
  }
  if (primaryFailed) {
    if (cleanupErrors.length > 0) {
      throw new AggregateError(
        [primaryError, ...cleanupErrors],
        primaryError instanceof Error ? primaryError.message : String(primaryError),
      );
    }
    throw primaryError;
  }
  if (cleanupErrors.length > 0) {
    const first = cleanupErrors[0];
    throw new AggregateError(
      cleanupErrors,
      first instanceof Error ? first.message : "materialize cleanup failed",
    );
  }
}

function parseJson(source: string): unknown {
  if (Buffer.byteLength(source, "utf8") > MAX_INPUT_BYTES) throw new Error("input exceeds 32 MiB");
  try { return JSON.parse(source); } catch { throw new Error("input must be valid JSON"); }
}

function main(): void {
  const options = parseArgs(process.argv.slice(2));
  if (options.command === "catalog") {
    writeOutput(options.output, `${JSON.stringify({ schemaVersion: "1.0", skills: MINIAPP_SKILL_CATALOG }, null, 2)}\n`);
    return;
  }
  const value = parseJson(readInput(options.input));
  if (options.command === "digest") {
    if (!value || typeof value !== "object" || Array.isArray(value) || !Array.isArray((value as { files?: unknown }).files)) throw new Error("digest input must be { files: [...] }");
    writeOutput(options.output, `${JSON.stringify({ schemaVersion: "1.0", sourceFileSetDigest: computeMiniappSourceFileSetDigest((value as { files: Parameters<typeof computeMiniappSourceFileSetDigest>[0] }).files) }, null, 2)}\n`);
    return;
  }
  const handlerInput = options.command === "package"
    ? { schemaVersion: "1.0", action: "run-package", packageInput: value }
    : value;
  const result = handleMiniappSkillRequest(handlerInput);
  if (options.materialize !== undefined) {
    if (!("generatedProjects" in result)) {
      throw new Error("--materialize requires action=run-all, action=run-package, or the package command");
    }
    materializeMiniappRun(result, options.materialize);
  }
  writeOutput(options.output, `${JSON.stringify(result, null, 2)}\n`);
}

if (process.argv[1] !== undefined
  && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    main();
  } catch (error) {
    const structured = error instanceof MiniappPackageContractError ? {
      state: error.state,
      code: error.code,
      path: error.path,
      error: error.message,
      details: error.details,
      certification: "NOT_CERTIFIED",
    } : {
      error: error instanceof Error ? error.message : String(error),
      certification: "NOT_CERTIFIED",
    };
    process.stderr.write(`${JSON.stringify(structured)}\n`);
    process.exitCode = 1;
  }
}
