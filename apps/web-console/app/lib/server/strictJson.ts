export class StrictJsonError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "StrictJsonError";
    this.code = code;
  }
}

const maximumDepth = 128;
const maximumValues = 100_000;

/** Validate JSON grammar while retaining object-pair identity before JSON.parse erases duplicates. */
export function parseStrictJson(text: string): unknown {
  let offset = 0;
  let values = 0;

  function fail(code = "INVALID_JSON"): never {
    throw new StrictJsonError(code);
  }

  function whitespace(): void {
    while (/\s/u.test(text[offset] ?? "")) offset += 1;
  }

  function stringValue(): string {
    if (text[offset] !== '"') fail();
    const start = offset;
    offset += 1;
    while (offset < text.length) {
      const code = text.charCodeAt(offset);
      if (code === 0x22) {
        offset += 1;
        try {
          const value = JSON.parse(text.slice(start, offset)) as unknown;
          if (typeof value !== "string") fail();
          return value;
        } catch {
          fail();
        }
      }
      if (code < 0x20) fail();
      if (code === 0x5c) {
        offset += 1;
        const escape = text[offset];
        if (escape === "u") {
          if (!/^[0-9a-fA-F]{4}$/.test(text.slice(offset + 1, offset + 5))) fail();
          offset += 5;
          continue;
        }
        if (!escape || !'"\\/bfnrt'.includes(escape)) fail();
      }
      offset += 1;
    }
    fail();
  }

  function value(depth: number): void {
    values += 1;
    if (depth > maximumDepth || values > maximumValues) fail("JSON_BUDGET_EXCEEDED");
    whitespace();
    const token = text[offset];
    if (token === "{") {
      offset += 1;
      whitespace();
      const keys = new Set<string>();
      if (text[offset] === "}") {
        offset += 1;
        return;
      }
      while (offset < text.length) {
        whitespace();
        const key = stringValue();
        if (keys.has(key)) fail("DUPLICATE_JSON_FIELD");
        keys.add(key);
        whitespace();
        if (text[offset] !== ":") fail();
        offset += 1;
        value(depth + 1);
        whitespace();
        if (text[offset] === "}") {
          offset += 1;
          return;
        }
        if (text[offset] !== ",") fail();
        offset += 1;
      }
      fail();
    }
    if (token === "[") {
      offset += 1;
      whitespace();
      if (text[offset] === "]") {
        offset += 1;
        return;
      }
      while (offset < text.length) {
        value(depth + 1);
        whitespace();
        if (text[offset] === "]") {
          offset += 1;
          return;
        }
        if (text[offset] !== ",") fail();
        offset += 1;
      }
      fail();
    }
    if (token === '"') {
      stringValue();
      return;
    }
    for (const literal of ["true", "false", "null"] as const) {
      if (text.startsWith(literal, offset)) {
        offset += literal.length;
        return;
      }
    }
    const number = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(
      text.slice(offset),
    );
    if (!number) fail();
    offset += number[0].length;
  }

  value(0);
  whitespace();
  if (offset !== text.length) fail();
  try {
    return JSON.parse(text) as unknown;
  } catch {
    fail();
  }
}
