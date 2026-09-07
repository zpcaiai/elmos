/**
 * Fail-closed boundary for the end-of-life Vue 2 compiler/runtime.
 *
 * Vue 2.7.16 has no upstream release containing the fixes for
 * GHSA-5j4c-8p2g-v4jx or GHSA-g3ch-rx76-35fx.  The exact Vue 2 route is
 * retained for compatibility evidence, so every compiler entry point must
 * reject inputs that can exercise the known parser ReDoS shape and must not
 * run in an already prototype-polluted isolate.
 */

export const MAX_VUE2_COMPILER_INPUT_BYTES = 1024 * 1024;

const prototypeSensitiveKeys = [
  "attrs",
  "attrsList",
  "classBinding",
  "events",
  "staticClass",
  "staticStyle",
  "styleBinding",
] as const;

const rawTextTags = ["script", "style", "textarea"] as const;

function templateRegion(source: string, mode: "sfc" | "template"): string {
  if (mode === "template") return source;
  const lower = source.toLowerCase();
  const opening = lower.indexOf("<template");
  if (opening < 0) return "";
  const openingEnd = lower.indexOf(">", opening + "<template".length);
  if (openingEnd < 0) return "";
  const closing = lower.indexOf("</template", openingEnd + 1);
  return closing < 0 ? source.slice(openingEnd + 1) : source.slice(openingEnd + 1, closing);
}

function containsOpeningTag(source: string, tag: string): boolean {
  const needle = `<${tag}`;
  let cursor = source.indexOf(needle);
  while (cursor >= 0) {
    const boundary = source[cursor + needle.length];
    if (boundary === undefined || boundary === ">" || boundary === "/" || /\s/u.test(boundary)) {
      return true;
    }
    cursor = source.indexOf(needle, cursor + needle.length);
  }
  return false;
}

export function assertVue2CompilerInput(
  source: string,
  label: string,
  mode: "sfc" | "template" = "sfc",
): void {
  const bytes = Buffer.byteLength(source, "utf8");
  if (bytes > MAX_VUE2_COMPILER_INPUT_BYTES) {
    throw new Error(`${label}: Vue 2 compiler input exceeds ${MAX_VUE2_COMPILER_INPUT_BYTES} UTF-8 bytes`);
  }

  for (const key of prototypeSensitiveKeys) {
    if (Object.prototype.hasOwnProperty.call(Object.prototype, key)) {
      throw new Error(`${label}: Vue 2 compiler blocked because Object.prototype.${key} is polluted`);
    }
  }

  const template = templateRegion(source, mode).toLowerCase();
  for (const tag of rawTextTags) {
    if (containsOpeningTag(template, tag)) {
      throw new Error(`${label}: Vue 2 compiler blocks <${tag}> in the certified template surface`);
    }
  }

  let consecutiveLt = 0;
  for (const character of template) {
    consecutiveLt = character === "<" ? consecutiveLt + 1 : 0;
    if (consecutiveLt > 256) {
      throw new Error(`${label}: Vue 2 compiler blocks an adversarial '<' sequence`);
    }
  }
}
