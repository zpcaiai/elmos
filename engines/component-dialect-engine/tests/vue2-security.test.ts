import { MAX_VUE2_COMPILER_INPUT_BYTES, assertVue2CompilerInput } from "../src/vue2-security";

describe("Vue 2 EOL compiler security boundary", () => {
  it("accepts the exact bounded certified SFC surface", () => {
    expect(() => assertVue2CompilerInput(
      '<template><main class="safe">Hello</main></template><script>export default {}</script>',
      "safe.vue",
    )).not.toThrow();
  });

  it("rejects oversized and known raw-text ReDoS shapes before the compiler", () => {
    expect(() => assertVue2CompilerInput("x".repeat(MAX_VUE2_COMPILER_INPUT_BYTES + 1), "large.vue"))
      .toThrow(/exceeds/);
    expect(() => assertVue2CompilerInput(
      `<template><script>${"<".repeat(512)}</textarea></template><script>export default {}</script>`,
      "redos.vue",
    )).toThrow(/blocks <script>/);
    expect(() => assertVue2CompilerInput(`<div>${"<".repeat(257)}</div>`, "redos-template", "template"))
      .toThrow(/adversarial/);
  });

  it("fails closed when compiler-sensitive prototype fields are polluted", () => {
    Object.defineProperty(Object.prototype, "staticClass", {
      configurable: true,
      enumerable: false,
      value: '"polluted"',
    });
    try {
      expect(() => assertVue2CompilerInput("<template><div /></template>", "polluted.vue"))
        .toThrow(/Object\.prototype\.staticClass is polluted/);
    } finally {
      delete (Object.prototype as { staticClass?: unknown }).staticClass;
    }
  });
});
