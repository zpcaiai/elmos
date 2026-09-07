export type StrictJsonLimits = {
  maximumDepth?: number;
  maximumNodes?: number;
};

export class StrictJsonError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.code = code;
    this.name = "StrictJsonError";
  }
}

const defaultMaximumDepth = 32;
const defaultMaximumNodes = 200_000;

function invalid(code: string): never {
  throw new StrictJsonError(code);
}

function skipWhitespace(source: string, offset: number): number {
  while (offset < source.length && /[\u0009\u000a\u000d\u0020]/.test(source[offset])) offset += 1;
  return offset;
}

function scanString(source: string, offset: number): number {
  if (source[offset] !== '"') invalid("JSON_INVALID");
  let cursor = offset + 1;
  while (cursor < source.length) {
    const code = source.charCodeAt(cursor);
    if (code === 0x22) return cursor + 1;
    if (code < 0x20) invalid("JSON_INVALID");
    if (code !== 0x5c) {
      cursor += 1;
      continue;
    }
    cursor += 1;
    const escaped = source[cursor];
    if (escaped === "u") {
      if (!/^[0-9a-fA-F]{4}$/.test(source.slice(cursor + 1, cursor + 5))) invalid("JSON_INVALID");
      cursor += 5;
      continue;
    }
    if (!escaped || !'"\\/bfnrt'.includes(escaped)) invalid("JSON_INVALID");
    cursor += 1;
  }
  return invalid("JSON_INVALID");
}

function consumeNode(budget: { remaining: number }): void {
  budget.remaining -= 1;
  if (budget.remaining < 0) invalid("JSON_TOO_COMPLEX");
}

function scanValue(
  source: string,
  offset: number,
  depth: number,
  maximumDepth: number,
  budget: { remaining: number },
): number {
  if (depth > maximumDepth) invalid("JSON_DEPTH_EXCEEDED");
  consumeNode(budget);
  let cursor = skipWhitespace(source, offset);
  if (source[cursor] === '"') return scanString(source, cursor);
  if (source[cursor] === "{") {
    cursor = skipWhitespace(source, cursor + 1);
    const keys = new Set<string>();
    if (source[cursor] === "}") return cursor + 1;
    while (cursor < source.length) {
      const start = cursor;
      const end = scanString(source, start);
      let key: unknown;
      try {
        key = JSON.parse(source.slice(start, end));
      } catch {
        return invalid("JSON_INVALID");
      }
      if (typeof key !== "string") invalid("JSON_INVALID");
      if (keys.has(key)) invalid("JSON_DUPLICATE_KEY");
      keys.add(key);
      cursor = skipWhitespace(source, end);
      if (source[cursor] !== ":") invalid("JSON_INVALID");
      cursor = scanValue(source, cursor + 1, depth + 1, maximumDepth, budget);
      cursor = skipWhitespace(source, cursor);
      if (source[cursor] === "}") return cursor + 1;
      if (source[cursor] !== ",") invalid("JSON_INVALID");
      cursor = skipWhitespace(source, cursor + 1);
    }
    return invalid("JSON_INVALID");
  }
  if (source[cursor] === "[") {
    cursor = skipWhitespace(source, cursor + 1);
    if (source[cursor] === "]") return cursor + 1;
    while (cursor < source.length) {
      cursor = scanValue(source, cursor, depth + 1, maximumDepth, budget);
      cursor = skipWhitespace(source, cursor);
      if (source[cursor] === "]") return cursor + 1;
      if (source[cursor] !== ",") invalid("JSON_INVALID");
      cursor = skipWhitespace(source, cursor + 1);
    }
    return invalid("JSON_INVALID");
  }
  const start = cursor;
  while (cursor < source.length && !/[\u0009\u000a\u000d\u0020,\]}]/.test(source[cursor])) cursor += 1;
  if (cursor === start) invalid("JSON_INVALID");
  return cursor;
}

function validUnicode(value: string): boolean {
  for (let cursor = 0; cursor < value.length; cursor += 1) {
    const code = value.charCodeAt(cursor);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(cursor + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      cursor += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return false;
    }
  }
  return true;
}

function validateTree(
  value: unknown,
  depth: number,
  maximumDepth: number,
  budget: { remaining: number },
): void {
  if (depth > maximumDepth) invalid("JSON_DEPTH_EXCEEDED");
  consumeNode(budget);
  if (typeof value === "number") {
    if (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value))) {
      invalid("JSON_NUMBER_INVALID");
    }
    return;
  }
  if (typeof value === "string") {
    if (!validUnicode(value)) invalid("JSON_UNICODE_INVALID");
    return;
  }
  if (value === null || typeof value === "boolean") return;
  if (Array.isArray(value)) {
    for (const item of value) validateTree(item, depth + 1, maximumDepth, budget);
    return;
  }
  if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (!validUnicode(key)) invalid("JSON_UNICODE_INVALID");
      validateTree(item, depth + 1, maximumDepth, budget);
    }
    return;
  }
  invalid("JSON_INVALID");
}

export function parseStrictJson(source: string, limits: StrictJsonLimits = {}): unknown {
  const maximumDepth = limits.maximumDepth ?? defaultMaximumDepth;
  const maximumNodes = limits.maximumNodes ?? defaultMaximumNodes;
  if (!Number.isSafeInteger(maximumDepth) || maximumDepth < 0) invalid("JSON_LIMIT_INVALID");
  if (!Number.isSafeInteger(maximumNodes) || maximumNodes < 1) invalid("JSON_LIMIT_INVALID");
  const end = scanValue(source, 0, 0, maximumDepth, { remaining: maximumNodes });
  if (skipWhitespace(source, end) !== source.length) invalid("JSON_INVALID");
  let value: unknown;
  try {
    value = JSON.parse(source);
  } catch {
    return invalid("JSON_INVALID");
  }
  validateTree(value, 0, maximumDepth, { remaining: maximumNodes });
  return value;
}

function canonicalEncode(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    const encoded = JSON.stringify(value);
    if (typeof encoded !== "string") invalid("JSON_INVALID");
    return encoded;
  }
  if (Array.isArray(value)) return `[${value.map(canonicalEncode).join(",")}]`;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalEncode(record[key])}`)
      .join(",")}}`;
  }
  return invalid("JSON_INVALID");
}

export function canonicalStrictJson(value: unknown, limits: StrictJsonLimits = {}): string {
  const maximumDepth = limits.maximumDepth ?? defaultMaximumDepth;
  const maximumNodes = limits.maximumNodes ?? defaultMaximumNodes;
  if (!Number.isSafeInteger(maximumDepth) || maximumDepth < 0) invalid("JSON_LIMIT_INVALID");
  if (!Number.isSafeInteger(maximumNodes) || maximumNodes < 1) invalid("JSON_LIMIT_INVALID");
  validateTree(value, 0, maximumDepth, { remaining: maximumNodes });
  return canonicalEncode(value);
}
