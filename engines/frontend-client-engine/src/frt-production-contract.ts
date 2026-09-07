import { Buffer } from "node:buffer";
import { createHash } from "node:crypto";

import { frtCatalog } from "./frt-catalog.generated.js";
import type { FrtAction, FrtFinding } from "./frt-types.js";

export type FrtCompiledExecutionContract =
  (typeof frtCatalog.skills)[number]["executionContract"];

const maximumDepth = 32;
const maximumNodes = 200_000;
const maximumContainerItems = 20_000;
const maximumStringBytes = 1_000_000;
const maximumSourceFiles = 512;
const maximumSourceBytes = 16 * 1024 * 1024;
const unsafeKeys = new Set(["__proto__", "prototype", "constructor"]);

function canonicalContractJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalContractJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalContractJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

export function digestFrtExecutionContract(contract: FrtCompiledExecutionContract): string {
  const { contractDigest: _declaredDigest, ...unsigned } = contract;
  return `sha256:${createHash("sha256").update(canonicalContractJson(unsigned)).digest("hex")}`;
}

function finding(code: string, message: string): FrtFinding {
  return {
    code,
    severity: "ERROR",
    message,
    owner: "request-owner",
    blocking: true,
  };
}

export function frtExecutionContractByKey(
  key: string,
): FrtCompiledExecutionContract | undefined {
  const normalized = key.trim().toLocaleLowerCase("en-US");
  return frtCatalog.skills.find(skill =>
    skill.id.toLocaleLowerCase("en-US") === normalized
      || skill.name.toLocaleLowerCase("en-US") === normalized,
  )?.executionContract;
}

function structuralFindings(value: unknown): readonly FrtFinding[] {
  const findings: FrtFinding[] = [];
  let nodes = 0;
  const visit = (item: unknown, path: string, depth: number): void => {
    nodes += 1;
    if (nodes > maximumNodes) {
      if (!findings.some(entry => entry.code === "FRT_INPUT_NODE_LIMIT_EXCEEDED")) {
        findings.push(finding("FRT_INPUT_NODE_LIMIT_EXCEEDED", `Input exceeds ${maximumNodes} JSON nodes.`));
      }
      return;
    }
    if (depth > maximumDepth) {
      findings.push(finding("FRT_INPUT_DEPTH_EXCEEDED", `${path} exceeds maximum depth ${maximumDepth}.`));
      return;
    }
    if (typeof item === "string") {
      if (Buffer.byteLength(item, "utf8") > maximumStringBytes) {
        findings.push(finding("FRT_INPUT_STRING_LIMIT_EXCEEDED", `${path} exceeds ${maximumStringBytes} UTF-8 bytes.`));
      }
      return;
    }
    if (typeof item === "number" && !Number.isFinite(item)) {
      findings.push(finding("FRT_INPUT_NUMBER_INVALID", `${path} must be a finite JSON number.`));
      return;
    }
    if (item === null || ["boolean", "number"].includes(typeof item)) return;
    if (Array.isArray(item)) {
      if (item.length > maximumContainerItems) {
        findings.push(finding("FRT_INPUT_CONTAINER_LIMIT_EXCEEDED", `${path} has too many array items.`));
        return;
      }
      item.forEach((child, index) => visit(child, `${path}[${index}]`, depth + 1));
      return;
    }
    if (typeof item !== "object") {
      findings.push(finding("FRT_INPUT_JSON_TYPE_INVALID", `${path} contains a non-JSON value.`));
      return;
    }
    const prototype = Object.getPrototypeOf(item);
    if (prototype !== Object.prototype && prototype !== null) {
      findings.push(finding("FRT_INPUT_OBJECT_PROTOTYPE_REJECTED", `${path} must be a plain JSON object.`));
      return;
    }
    const entries = Object.entries(item as Record<string, unknown>);
    if (entries.length > maximumContainerItems) {
      findings.push(finding("FRT_INPUT_CONTAINER_LIMIT_EXCEEDED", `${path} has too many object fields.`));
      return;
    }
    for (const [key, child] of entries) {
      if (!key || key.length > 256 || unsafeKeys.has(key)) {
        findings.push(finding("FRT_INPUT_KEY_REJECTED", `${path} contains an unsafe or oversized key.`));
        continue;
      }
      visit(child, `${path}.${key}`, depth + 1);
    }
  };
  visit(value, "input", 0);
  return findings;
}

function sourceFileFindings(input: Readonly<Record<string, unknown>>): readonly FrtFinding[] {
  if (input.files === undefined) return [];
  if (!input.files || typeof input.files !== "object" || Array.isArray(input.files)) {
    return [finding("FRT_SOURCE_FILES_INVALID", "input.files must be an object of relative paths to UTF-8 source text.")];
  }
  const entries = Object.entries(input.files as Record<string, unknown>);
  const findings: FrtFinding[] = [];
  let totalBytes = 0;
  if (entries.length === 0 || entries.length > maximumSourceFiles) {
    findings.push(finding("FRT_SOURCE_FILE_COUNT_INVALID", `input.files must contain 1-${maximumSourceFiles} files.`));
  }
  for (const [path, content] of entries) {
    if (!path || path.length > 512 || path.startsWith("/") || path.includes("\\")
        || path.split("/").some(segment => !segment || segment === "." || segment === "..")) {
      findings.push(finding("FRT_SOURCE_PATH_INVALID", `Source path ${JSON.stringify(path)} is not a safe normalized relative path.`));
      continue;
    }
    if (typeof content !== "string") {
      findings.push(finding("FRT_SOURCE_CONTENT_INVALID", `Source path ${path} must contain UTF-8 text.`));
      continue;
    }
    totalBytes += Buffer.byteLength(content, "utf8");
  }
  if (totalBytes > maximumSourceBytes) {
    findings.push(finding("FRT_SOURCE_BYTES_LIMIT_EXCEEDED", `Source input exceeds ${maximumSourceBytes} UTF-8 bytes.`));
  }
  return findings;
}

/**
 * Validates the per-Skill input contract before a handler sees it. The compiler emits
 * one exact contract for every source Skill; unknown top-level fields cannot silently
 * disappear inside a shared handler, and direct engine clients receive the same limits
 * as the Web BFF.
 */
export function validateFrtProductionInput(
  contract: FrtCompiledExecutionContract,
  action: FrtAction,
  input: Readonly<Record<string, unknown>> | undefined,
): readonly FrtFinding[] {
  if (action === "VERIFY" && input !== undefined) {
    return [finding("FRT_VERIFY_INPUT_NOT_ALLOWED", "VERIFY consumes independently signed evidence, not mutable handler input.")];
  }
  const required = contract.inputContract.required as readonly string[];
  const optional = contract.inputContract.optional as readonly string[];
  const allowed = new Set([...required, ...optional]);
  const findings: FrtFinding[] = [];
  if (input !== undefined) {
    findings.push(...structuralFindings(input), ...sourceFileFindings(input));
    for (const key of Object.keys(input)) {
      if (!allowed.has(key)) {
        findings.push(finding(
          "FRT_HANDLER_INPUT_UNKNOWN",
          `${contract.skillId} does not declare input.${key}; unknown input cannot be ignored.`,
        ));
      }
    }
  }
  if (action === "ANALYZE" || action === "EXECUTE") {
    for (const key of required) {
      if (input?.[key] === undefined) {
        findings.push(finding(
          "FRT_HANDLER_INPUT_REQUIRED",
          `${contract.skillId} requires input.${key} before ${action}.`,
        ));
      }
    }
  }
  return findings;
}

export function assertFRTContractRegistry(): void {
  const ids = new Set<string>();
  const names = new Set<string>();
  const capabilities = new Set<string>();
  const digests = new Set<string>();
  for (const skill of frtCatalog.skills) {
    const contract = skill.executionContract;
    if (contract.skillId !== skill.id || contract.skillName !== skill.name
        || contract.batch !== skill.batch || contract.handlerKind !== skill.handlerKind
        || contract.sourceSha256 !== skill.sourceSha256
        || !/^sha256:[a-f0-9]{64}$/.test(contract.contractDigest)
        || digestFrtExecutionContract(contract) !== contract.contractDigest
        || contract.productionOperationAuthority !== "EXTERNAL_ONLY"
        || contract.certification !== "NOT_CERTIFIED") {
      throw new Error(`FRT_COMPILED_CONTRACT_IDENTITY_INVALID:${skill.id}`);
    }
    if (ids.has(contract.skillId) || names.has(contract.skillName)
        || capabilities.has(contract.capabilityKey) || digests.has(contract.contractDigest)) {
      throw new Error(`FRT_COMPILED_CONTRACT_DUPLICATED:${skill.id}`);
    }
    ids.add(contract.skillId);
    names.add(contract.skillName);
    capabilities.add(contract.capabilityKey);
    digests.add(contract.contractDigest);
  }
  if (ids.size !== 472) throw new Error(`FRT_COMPILED_CONTRACT_COUNT_INVALID:${ids.size}`);
}
