import assert from "node:assert/strict";
import test from "node:test";

import { MAX_VUE2_COMPILER_INPUT_BYTES, assertVue2CompilerInput } from "../src/vue2-security.js";

test("Vue 2 compiler guard accepts a bounded certified SFC", () => {
  assert.doesNotThrow(() => assertVue2CompilerInput(
    '<template><main class="safe">Hello</main></template><script>export default {}</script>',
    "safe.vue",
  ));
});

test("Vue 2 compiler guard rejects oversized and raw-text ReDoS inputs", () => {
  assert.throws(
    () => assertVue2CompilerInput("x".repeat(MAX_VUE2_COMPILER_INPUT_BYTES + 1), "large.vue"),
    /exceeds/u,
  );
  assert.throws(
    () => assertVue2CompilerInput(
      `<template><script>${"<".repeat(512)}</textarea></template><script>export default {}</script>`,
      "redos.vue",
    ),
    /blocks <script>/u,
  );
});

test("Vue 2 compiler guard rejects prototype-polluted compiler state", () => {
  Object.defineProperty(Object.prototype, "staticStyle", {
    configurable: true,
    enumerable: false,
    value: '"polluted"',
  });
  try {
    assert.throws(
      () => assertVue2CompilerInput("<template><main /></template>", "polluted.vue"),
      /Object\.prototype\.staticStyle is polluted/u,
    );
  } finally {
    delete (Object.prototype as { staticStyle?: unknown }).staticStyle;
  }
});
