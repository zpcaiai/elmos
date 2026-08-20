import { GenerationRunnerError } from "./generationRunner";

const maximumRequestBytes = 8 * 1024;

function skipWhitespace(source: string, start: number): number {
  let cursor = start;
  while (cursor < source.length && /\s/.test(source[cursor])) cursor += 1;
  return cursor;
}

function jsonStringEnd(source: string, start: number): number {
  let escaped = false;
  for (let cursor = start + 1; cursor < source.length; cursor += 1) {
    const character = source[cursor];
    if (escaped) escaped = false;
    else if (character === "\\") escaped = true;
    else if (character === '"') return cursor + 1;
  }
  throw new SyntaxError("unterminated JSON string");
}

export function rejectDuplicateTopLevelJsonFields(source: string): void {
  let cursor = skipWhitespace(source, 0);
  if (source[cursor] !== "{") return;
  cursor = skipWhitespace(source, cursor + 1);
  if (source[cursor] === "}") return;
  const observed = new Set<string>();
  while (cursor < source.length) {
    if (source[cursor] !== '"') throw new SyntaxError("invalid JSON object key");
    const keyEnd = jsonStringEnd(source, cursor);
    const key = JSON.parse(source.slice(cursor, keyEnd)) as string;
    if (observed.has(key)) {
      throw new GenerationRunnerError(400, "TRANSLATION_REQUEST_DUPLICATE_FIELD");
    }
    observed.add(key);
    cursor = skipWhitespace(source, keyEnd);
    if (source[cursor] !== ":") throw new SyntaxError("invalid JSON object member");
    cursor = skipWhitespace(source, cursor + 1);
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (; cursor < source.length; cursor += 1) {
      const character = source[cursor];
      if (inString) {
        if (escaped) escaped = false;
        else if (character === "\\") escaped = true;
        else if (character === '"') inString = false;
        continue;
      }
      if (character === '"') inString = true;
      else if (character === "{" || character === "[") depth += 1;
      else if (character === "}" || character === "]") {
        if (depth > 0) depth -= 1;
        else if (character === "}") break;
      } else if (character === "," && depth === 0) break;
    }
    if (source[cursor] === "}") return;
    if (source[cursor] !== ",") throw new SyntaxError("invalid JSON object separator");
    cursor = skipWhitespace(source, cursor + 1);
  }
  throw new SyntaxError("unterminated JSON object");
}

export async function readBoundedTranslationRequest(request: Request): Promise<string> {
  const declaredLength = request.headers.get("content-length");
  if (declaredLength !== null) {
    if (!/^(0|[1-9][0-9]*)$/.test(declaredLength)) {
      throw new GenerationRunnerError(400, "TRANSLATION_CONTENT_LENGTH_INVALID");
    }
    if (Number(declaredLength) > maximumRequestBytes) {
      throw new GenerationRunnerError(413, "REQUEST_TOO_LARGE");
    }
  }
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > maximumRequestBytes) {
        await reader.cancel("REQUEST_TOO_LARGE").catch(() => undefined);
        throw new GenerationRunnerError(413, "REQUEST_TOO_LARGE");
      }
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel(error).catch(() => undefined);
    throw error;
  }
  const bytes = Buffer.concat(chunks.map((chunk) => Buffer.from(chunk)));
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new GenerationRunnerError(400, "TRANSLATION_REQUEST_UTF8_INVALID");
  }
}
