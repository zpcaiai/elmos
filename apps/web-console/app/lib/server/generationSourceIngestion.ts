import { createHash } from "node:crypto";
import { promises as dns } from "node:dns";
import { lstat, readFile, realpath } from "node:fs/promises";
import { request as httpsRequest } from "node:https";
import net from "node:net";
import path from "node:path";
import { convert } from "html-to-text";
import mammoth from "mammoth";
import type {
  GenerationSourceBundle,
  GenerationSourceKind,
  GenerationSourceReference,
} from "../contracts";

const MAX_FILES = 8;
const MAX_SOURCES = 26;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const MAX_FETCH_BYTES = 2 * 1024 * 1024;
const MAX_SOURCE_CHARACTERS = 80_000;
const MAX_COMBINED_CHARACTERS = 32_000;
const MAX_PDF_PAGES = 200;
const FETCH_TIMEOUT_MS = 10_000;
const MAX_REDIRECTS = 3;
const sourceNamePattern = /^[a-z0-9][a-z0-9-]{1,63}$/;

export type RepositoryRequirementSource = {
  path: string;
  mediaType: string;
  origin: string;
  raw: Buffer;
  warnings: string[];
};

type UploadedSource = {
  name: string;
  type: string;
  size: number;
  arrayBuffer(): Promise<ArrayBuffer>;
};

type ExtractedSource = {
  kind: GenerationSourceKind;
  label: string;
  mediaType: string;
  origin?: string;
  raw: Buffer;
  text: string;
  warnings: string[];
};

class SourceIngestionError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map(
    (key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`,
  ).join(",")}}`;
}

function sha256(value: Buffer | string): string {
  return createHash("sha256").update(value).digest("hex");
}

function normalizeText(value: string): string {
  return value
    .replace(/^\uFEFF/, "")
    .replace(/\r\n?/g, "\n")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .split("\n")
    .map((line) => line.replace(/[^\S\n]+/g, " ").trimEnd())
    .join("\n")
    .replace(/\n{4,}/g, "\n\n\n")
    .trim();
}

function decodeUtf8(raw: Buffer): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(raw);
  } catch {
    throw new SourceIngestionError(422, "SOURCE_TEXT_MUST_BE_UTF8");
  }
}

function safeLabel(value: string): string {
  const label = path.basename(value).replace(/[\u0000-\u001F\u007F]/g, "").trim();
  if (!label || label.length > 180) {
    throw new SourceIngestionError(400, "SOURCE_LABEL_INVALID");
  }
  return label;
}

function htmlToText(html: string): string {
  return convert(html, {
    baseElements: { selectors: ["main", "article", "body"] },
    limits: {
      maxChildNodes: 100_000,
      maxDepth: 80,
      maxBaseElements: 3,
    },
    selectors: [
      { selector: "script", format: "skip" },
      { selector: "style", format: "skip" },
      { selector: "noscript", format: "skip" },
      { selector: "svg", format: "skip" },
      { selector: "img", format: "skip" },
      { selector: "a", options: { ignoreHref: true } },
    ],
    wordwrap: false,
  });
}

async function extractPdf(raw: Buffer): Promise<string> {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const loadingTask = pdfjs.getDocument({
    data: new Uint8Array(raw),
    useSystemFonts: true,
    useWasm: false,
    stopAtErrors: true,
  });
  const document = await loadingTask.promise;
  try {
    if (document.numPages > MAX_PDF_PAGES) {
      throw new SourceIngestionError(422, "PDF_PAGE_LIMIT_EXCEEDED");
    }
    const pages: string[] = [];
    for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
      const page = await document.getPage(pageNumber);
      const content = await page.getTextContent();
      pages.push(content.items.map((item) => (
        typeof item === "object" && item !== null && "str" in item
          ? String(item.str)
          : ""
      )).join(" "));
      if (pages.join("\n").length > MAX_SOURCE_CHARACTERS) break;
    }
    const text = normalizeText(pages.join("\n\n"));
    if (!text) {
      throw new SourceIngestionError(422, "PDF_TEXT_NOT_FOUND_OCR_REQUIRED");
    }
    return text;
  } finally {
    await loadingTask.destroy();
  }
}

async function extractUploadedSource(file: UploadedSource): Promise<ExtractedSource> {
  if (file.size <= 0 || file.size > MAX_FILE_BYTES) {
    throw new SourceIngestionError(413, "SOURCE_FILE_SIZE_INVALID");
  }
  const label = safeLabel(file.name);
  const extension = path.extname(label).toLowerCase();
  const raw = Buffer.from(await file.arrayBuffer());
  if (raw.byteLength !== file.size || raw.byteLength > MAX_FILE_BYTES) {
    throw new SourceIngestionError(413, "SOURCE_FILE_SIZE_MISMATCH");
  }
  let text: string;
  let kind: GenerationSourceKind;
  let mediaType: string;
  const warnings: string[] = [];

  if (extension === ".txt") {
    kind = "text-file";
    mediaType = "text/plain";
    text = decodeUtf8(raw);
  } else if (extension === ".md" || extension === ".markdown") {
    kind = "markdown-file";
    mediaType = "text/markdown";
    text = decodeUtf8(raw);
  } else if (extension === ".html" || extension === ".htm") {
    kind = "html-file";
    mediaType = "text/html";
    text = htmlToText(decodeUtf8(raw));
  } else if (extension === ".docx") {
    kind = "word-file";
    mediaType = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    const result = await mammoth.extractRawText({ buffer: raw });
    text = result.value;
    warnings.push(...result.messages.map((message) => `WORD_${message.type.toUpperCase()}`));
  } else if (extension === ".pdf") {
    kind = "pdf-file";
    mediaType = "application/pdf";
    text = await extractPdf(raw);
  } else if (extension === ".doc") {
    throw new SourceIngestionError(415, "LEGACY_DOC_UNSUPPORTED_CONVERT_TO_DOCX");
  } else {
    throw new SourceIngestionError(415, "SOURCE_FILE_TYPE_UNSUPPORTED");
  }

  text = normalizeText(text);
  if (text.length < 3) {
    throw new SourceIngestionError(422, "SOURCE_TEXT_EMPTY");
  }
  return { kind, label, mediaType, raw, text, warnings };
}

function isPublicAddress(address: string, family: number): boolean {
  if (family === 4) {
    const parts = address.split(".").map(Number);
    if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
      return false;
    }
    const [a, b] = parts;
    return !(
      a === 0
      || a === 10
      || a === 127
      || (a === 100 && b >= 64 && b <= 127)
      || (a === 169 && b === 254)
      || (a === 172 && b >= 16 && b <= 31)
      || (a === 192 && (b === 0 || b === 168))
      || (a === 198 && (b === 18 || b === 19 || b === 51))
      || (a === 203 && b === 0)
      || a >= 224
    );
  }
  const normalized = address.toLowerCase();
  return family === 6
    && normalized !== "::"
    && normalized !== "::1"
    && !normalized.startsWith("fc")
    && !normalized.startsWith("fd")
    && !/^fe[89ab]/.test(normalized)
    && !normalized.startsWith("ff")
    && !normalized.startsWith("2001:db8")
    && !normalized.startsWith("::ffff:");
}

function publicOrigin(url: URL): string {
  const sanitized = new URL(url);
  sanitized.username = "";
  sanitized.password = "";
  sanitized.search = "";
  sanitized.hash = "";
  return sanitized.toString();
}

async function fetchOnlineHtml(
  input: string,
  redirectsRemaining = MAX_REDIRECTS,
): Promise<{ raw: Buffer; finalUrl: URL; mediaType: string }> {
  let url: URL;
  try {
    url = new URL(input);
  } catch {
    throw new SourceIngestionError(400, "SOURCE_URL_INVALID");
  }
  if (
    url.protocol !== "https:"
    || url.username
    || url.password
    || (url.port && url.port !== "443")
    || url.hostname.length > 253
  ) {
    throw new SourceIngestionError(400, "SOURCE_URL_HTTPS_PUBLIC_REQUIRED");
  }
  const addresses = await dns.lookup(url.hostname, { all: true, verbatim: true });
  if (
    addresses.length === 0
    || addresses.some((address) => !isPublicAddress(address.address, address.family))
  ) {
    throw new SourceIngestionError(400, "SOURCE_URL_PRIVATE_ADDRESS_BLOCKED");
  }
  const selected = addresses[0];
  return new Promise((resolve, reject) => {
    const request = httpsRequest(url, {
      headers: {
        "Accept": "text/html,application/xhtml+xml;q=0.9",
        "Accept-Encoding": "identity",
        "User-Agent": "ELMOS-Project-Synthesis-Source-Reader/1.0",
      },
      lookup: (_hostname, _options, callback) => {
        callback(null, selected.address, selected.family);
      },
    }, (response) => {
      const status = response.statusCode ?? 0;
      if (status >= 300 && status < 400 && response.headers.location) {
        response.resume();
        if (redirectsRemaining <= 0) {
          reject(new SourceIngestionError(422, "SOURCE_URL_REDIRECT_LIMIT_EXCEEDED"));
          return;
        }
        const redirected = new URL(response.headers.location, url);
        void fetchOnlineHtml(redirected.toString(), redirectsRemaining - 1).then(resolve, reject);
        return;
      }
      if (status < 200 || status >= 300) {
        response.resume();
        reject(new SourceIngestionError(422, `SOURCE_URL_HTTP_STATUS_${status}`));
        return;
      }
      const contentType = String(response.headers["content-type"] ?? "")
        .split(";", 1)[0].trim().toLowerCase();
      if (!["text/html", "application/xhtml+xml"].includes(contentType)) {
        response.resume();
        reject(new SourceIngestionError(415, "SOURCE_URL_HTML_CONTENT_TYPE_REQUIRED"));
        return;
      }
      const chunks: Buffer[] = [];
      let total = 0;
      response.on("data", (chunk: Buffer) => {
        total += chunk.byteLength;
        if (total > MAX_FETCH_BYTES) {
          request.destroy(new SourceIngestionError(413, "SOURCE_URL_RESPONSE_TOO_LARGE"));
          return;
        }
        chunks.push(chunk);
      });
      response.once("end", () => resolve({
        raw: Buffer.concat(chunks),
        finalUrl: url,
        mediaType: contentType,
      }));
    });
    request.setTimeout(FETCH_TIMEOUT_MS, () => {
      request.destroy(new SourceIngestionError(504, "SOURCE_URL_TIMEOUT"));
    });
    request.once("error", reject);
    request.end();
  });
}

async function extractOnlineSource(url: string): Promise<ExtractedSource> {
  const { raw, finalUrl, mediaType } = await fetchOnlineHtml(url);
  const text = normalizeText(htmlToText(decodeUtf8(raw)));
  if (text.length < 3) {
    throw new SourceIngestionError(422, "SOURCE_URL_TEXT_EMPTY");
  }
  return {
    kind: "online-html",
    label: safeLabel(finalUrl.hostname + finalUrl.pathname),
    mediaType,
    origin: publicOrigin(finalUrl),
    raw,
    text,
    warnings: [],
  };
}

async function extractSkillSource(
  repositoryRoot: string,
  rawName: string,
): Promise<ExtractedSource> {
  const name = rawName.trim();
  if (!sourceNamePattern.test(name)) {
    throw new SourceIngestionError(400, "SOURCE_SKILL_NAME_INVALID");
  }
  const roots = [
    path.join(/* turbopackIgnore: true */ repositoryRoot, ".agents", "skills"),
    path.join(/* turbopackIgnore: true */ repositoryRoot, "agent-skills", "runtime"),
  ];
  let raw: Buffer | undefined;
  let selected: string | undefined;
  for (const configuredRoot of roots) {
    try {
      const allowedRoot = await realpath(/* turbopackIgnore: true */ configuredRoot);
      const candidate = path.join(/* turbopackIgnore: true */ allowedRoot, name, "SKILL.md");
      const info = await lstat(/* turbopackIgnore: true */ candidate);
      const resolved = await realpath(/* turbopackIgnore: true */ candidate);
      if (
        info.isSymbolicLink()
        || !info.isFile()
        || (resolved !== allowedRoot && !resolved.startsWith(`${allowedRoot}${path.sep}`))
      ) {
        throw new SourceIngestionError(400, "SOURCE_SKILL_PATH_UNSAFE");
      }
      const loaded = await readFile(/* turbopackIgnore: true */ resolved);
      if (loaded.byteLength > MAX_FILE_BYTES) {
        throw new SourceIngestionError(413, "SOURCE_SKILL_TOO_LARGE");
      }
      raw = loaded;
      selected = resolved;
      break;
    } catch (error) {
      if (error instanceof SourceIngestionError) throw error;
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
  if (!raw || !selected) {
    throw new SourceIngestionError(404, `SOURCE_SKILL_NOT_FOUND:${name}`);
  }
  const text = normalizeText(decodeUtf8(raw));
  return {
    kind: "skill",
    label: name,
    mediaType: "text/markdown",
    origin: path.relative(repositoryRoot, selected),
    raw,
    text,
    warnings: ["SKILL_IMPORTED_AS_UNTRUSTED_REQUIREMENTS_NOT_EXECUTED"],
  };
}

function buildReferences(
  extracted: ExtractedSource[],
): { references: GenerationSourceReference[]; combinedText: string; warnings: string[] } {
  const allowance = Math.max(
    1_200,
    Math.min(12_000, Math.floor((MAX_COMBINED_CHARACTERS - extracted.length * 180) / extracted.length)),
  );
  const references: GenerationSourceReference[] = [];
  const sections: string[] = [];
  const warnings = new Set<string>();
  for (const [index, source] of extracted.entries()) {
    const originalCharacters = source.text.length;
    const limitedSource = source.text.slice(0, MAX_SOURCE_CHARACTERS);
    const included = limitedSource.slice(0, allowance);
    const truncated = originalCharacters > included.length;
    const sourceWarnings = [...source.warnings];
    if (truncated) sourceWarnings.push("SOURCE_TEXT_TRUNCATED_FOR_SYNTHESIS");
    sourceWarnings.forEach((warning) => warnings.add(warning));
    const reference: GenerationSourceReference = {
      id: `SRC-${String(index + 1).padStart(3, "0")}`,
      kind: source.kind,
      label: source.label,
      mediaType: source.mediaType,
      ...(source.origin ? { origin: source.origin } : {}),
      sha256: sha256(source.raw),
      byteCount: source.raw.byteLength,
      extractedCharacters: originalCharacters,
      includedCharacters: included.length,
      truncated,
      warnings: sourceWarnings,
    };
    references.push(reference);
    sections.push(
      `[来源 ${reference.id} · ${reference.kind} · ${reference.label} · SHA256 ${reference.sha256}]\n${included}`,
    );
  }
  const combinedText = normalizeText(sections.join("\n\n"));
  if (combinedText.length > MAX_COMBINED_CHARACTERS) {
    throw new SourceIngestionError(422, "SOURCE_BUNDLE_TEXT_LIMIT_EXCEEDED");
  }
  return { references, combinedText, warnings: [...warnings].sort() };
}

export async function buildGenerationSourceBundle(input: {
  description?: string;
  url?: string;
  skillNames?: string[];
  files?: UploadedSource[];
  repositorySources?: RepositoryRequirementSource[];
  repositoryRoot: string;
}): Promise<GenerationSourceBundle> {
  const extracted: ExtractedSource[] = [];
  const description = normalizeText(input.description ?? "");
  if (description) {
    extracted.push({
      kind: "description",
      label: "页面简述",
      mediaType: "text/plain",
      raw: Buffer.from(description, "utf-8"),
      text: description,
      warnings: [],
    });
  }
  const files = input.files ?? [];
  if (files.length > MAX_FILES) {
    throw new SourceIngestionError(413, "SOURCE_FILE_COUNT_EXCEEDED");
  }
  for (const file of files) extracted.push(await extractUploadedSource(file));
  if (input.url?.trim()) extracted.push(await extractOnlineSource(input.url.trim()));
  const skillNames = [...new Set(input.skillNames ?? [])];
  if (skillNames.length > 8) {
    throw new SourceIngestionError(413, "SOURCE_SKILL_COUNT_EXCEEDED");
  }
  for (const skillName of skillNames) {
    extracted.push(await extractSkillSource(input.repositoryRoot, skillName));
  }
  for (const source of input.repositorySources ?? []) {
    if (
      source.raw.byteLength < 1
      || source.raw.byteLength > MAX_FILE_BYTES
      || source.origin.length < 1
      || source.origin.length > 2_000
    ) {
      throw new SourceIngestionError(413, "SOURCE_REPOSITORY_FILE_INVALID");
    }
    const text = normalizeText(decodeUtf8(source.raw));
    if (text.length < 3) {
      throw new SourceIngestionError(422, "SOURCE_REPOSITORY_TEXT_EMPTY");
    }
    extracted.push({
      kind: "repository-file",
      label: safeLabel(source.path),
      mediaType: source.mediaType,
      origin: source.origin,
      raw: source.raw,
      text,
      warnings: source.warnings,
    });
  }
  if (extracted.length > MAX_SOURCES) {
    throw new SourceIngestionError(413, "GENERATION_SOURCE_COUNT_EXCEEDED");
  }
  if (extracted.length === 0) {
    throw new SourceIngestionError(400, "GENERATION_SOURCE_REQUIRED");
  }
  const { references, combinedText, warnings } = buildReferences(extracted);
  const bundleSha256 = sha256(canonicalJson({ description: combinedText, sources: references }));
  return {
    status: "READY_FOR_REVIEW",
    schemaVersion: "1.0.0",
    bundleSha256,
    combinedText,
    sources: references,
    warnings,
    extractedAt: new Date().toISOString(),
  };
}

export function sourceIngestionError(error: unknown): { status: number; reason: string } {
  if (error instanceof SourceIngestionError) {
    return { status: error.status, reason: error.message };
  }
  return {
    status: 422,
    reason: error instanceof Error ? error.message : "SOURCE_INGESTION_FAILED",
  };
}
