/** Fail-closed guard for the exact, end-of-life Vue 2.7.16 source route. */

export const MAX_VUE2_COMPILER_INPUT_BYTES = 1024 * 1024;

const compilerPrototypeKeys = [
  "attrs",
  "attrsList",
  "classBinding",
  "events",
  "staticClass",
  "staticStyle",
  "styleBinding",
] as const;

function templateRegion(source: string): string {
  const lower = source.toLowerCase();
  const opening = lower.indexOf("<template");
  if (opening < 0) return "";
  const openingEnd = lower.indexOf(">", opening + "<template".length);
  if (openingEnd < 0) return "";
  const closing = lower.indexOf("</template", openingEnd + 1);
  return closing < 0 ? source.slice(openingEnd + 1) : source.slice(openingEnd + 1, closing);
}

function hasOpeningTag(source: string, tag: string): boolean {
  const needle = `<${tag}`;
  let cursor = source.indexOf(needle);
  while (cursor >= 0) {
    const boundary = source[cursor + needle.length];
    if (boundary === undefined || boundary === ">" || boundary === "/" || /\s/u.test(boundary)) return true;
    cursor = source.indexOf(needle, cursor + needle.length);
  }
  return false;
}

export function assertVue2CompilerInput(source: string, label: string): void {
  if (Buffer.byteLength(source, "utf8") > MAX_VUE2_COMPILER_INPUT_BYTES) {
    throw new Error(`${label}: Vue 2 compiler input exceeds ${MAX_VUE2_COMPILER_INPUT_BYTES} UTF-8 bytes`);
  }
  for (const key of compilerPrototypeKeys) {
    if (Object.prototype.hasOwnProperty.call(Object.prototype, key)) {
      throw new Error(`${label}: Vue 2 compiler blocked because Object.prototype.${key} is polluted`);
    }
  }
  const template = templateRegion(source).toLowerCase();
  for (const tag of ["script", "style", "textarea"] as const) {
    if (hasOpeningTag(template, tag)) {
      throw new Error(`${label}: Vue 2 compiler blocks <${tag}> in the analyzed template surface`);
    }
  }
  let consecutiveLt = 0;
  for (const character of template) {
    consecutiveLt = character === "<" ? consecutiveLt + 1 : 0;
    if (consecutiveLt > 256) throw new Error(`${label}: Vue 2 compiler blocks an adversarial '<' sequence`);
  }
}
