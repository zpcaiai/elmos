import { computeMiniappSourceFileSetDigest, type MiniappConversionExecutionInput } from "../src/miniapp-skill-runtime.js";
import type { MiniappConversionRequest, MiniappInventoryInputFile, MiniappPlatform, MiniappSourceLabel } from "../src/miniapp-types.js";

export const vueTodoFiles: readonly MiniappInventoryInputFile[] = [
  {
    path: "package.json",
    content: JSON.stringify({
      name: "todo",
      version: "1.0.0",
      engines: { node: "24.3.0" },
      dependencies: { vue: "3.5.39", "vue-router": "4.5.0", pinia: "2.3.1" },
      devDependencies: { typescript: "5.9.2", vite: "6.0.0" },
    }),
  },
  {
    path: "package-lock.json",
    content: JSON.stringify({
      name: "todo",
      lockfileVersion: 3,
      packages: {
        "": {
          dependencies: { vue: "3.5.39", "vue-router": "4.5.0", pinia: "2.3.1" },
          devDependencies: { typescript: "5.9.2", vite: "6.0.0" },
          engines: { node: "24.3.0" },
        },
        "node_modules/vue": { version: "3.5.39" },
        "node_modules/vue-router": { version: "4.5.0" },
        "node_modules/pinia": { version: "2.3.1" },
        "node_modules/typescript": { version: "5.9.2" },
        "node_modules/vite": { version: "6.0.0" },
      },
    }),
  },
  {
    path: "src/App.vue",
    content: `<script setup lang="ts">import { ref } from "vue"; import { useTodoStore } from "./store"; const title = ref(""); const todos = useTodoStore(); function submit(){ todos.add(title.value); title.value = ""; }</script>
<template><div class="page"><span aria-label="Todo list">Todos</span><div class="form-body"><input v-model="title" aria-label="Todo text" required/><button :disabled="!title.trim()" @click="submit">Add</button><div class="todo-list"><span v-for="(item, index) in todos.items" :key="item + '-' + index">{{ item }}</span></div></div></div></template>
<style>.page { padding: 16px; color: #111827; }</style>`,
  },
  {
    path: "src/store.ts",
    content: `import { defineStore } from "pinia"; export const useTodoStore = defineStore("todos", { state: () => ({ items: [] as string[] }), actions: { add(text: string) { const value = text.trim(); if (value) this.items.push(value); } } });`,
  },
  {
    path: "src/router.ts",
    content: `import { createRouter, createWebHistory } from "vue-router"; export default createRouter({ history: createWebHistory("/"), routes: [{ path: "/", component: "App" }] });`,
  },
];

export function miniappRequest(
  files: readonly MiniappInventoryInputFile[] = vueTodoFiles,
  sourceLabel: MiniappSourceLabel = "vue3",
  targets: readonly MiniappPlatform[] = ["wechat", "alipay", "douyin", "xiaohongshu"],
): MiniappConversionRequest {
  const snapshotDigest = computeMiniappSourceFileSetDigest(files);
  return {
    schemaVersion: "1.0",
    requestId: `conv-${sourceLabel.replaceAll("-", "")}-fixture`,
    tenantId: "tenant-fixture",
    source: {
      root: "fixture",
      revision: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      snapshotDigest,
      sourceLabel,
      frameworkVersion: sourceLabel === "vue2" ? "2.7.16"
        : sourceLabel === "vue3" ? "3.5.39"
          : sourceLabel === "react" ? "19.2.0"
            : sourceLabel === "taro" ? "4.1.0"
              : sourceLabel === "uni-app" ? "3.0.0"
                : "1.0.0",
      languageVersion: "5.9.2",
      runtimeVersion: "24.3.0",
      buildToolVersion: "6.0.0",
    },
    targets: targets.map(platform => platform === "wechat"
      ? { platform, platformVersion: "3.9.1", toolchainVersion: "1.06.2504010" }
      : platform === "alipay"
        ? { platform, platformVersion: "2.10.2", toolchainVersion: "3.9.4" }
        : { platform, platformVersion: "1.0.0", toolchainVersion: "1.0.0" }),
    policy: {
      priority: "balanced",
      webviewFallback: "deny",
      fullPageCanvasFallback: "deny",
      unsupportedPolicy: "block",
      limits: { maxFileCount: 100, maxFileBytes: 1_048_576, maxTotalBytes: 10_485_760 },
      secretReferences: [],
    },
    evidence: [{
      role: "source-snapshot",
      uri: "artifact://source/snapshot",
      digest: snapshotDigest,
      state: "PASSED",
      executor: "fixture-executor",
      verifier: "fixture-verifier",
      synthetic: false,
      byteCount: files.reduce((total, file) => total + (typeof file.content === "string" ? Buffer.byteLength(file.content, "utf8") : file.content.byteLength), 0),
    }],
  };
}

export function conversionInput(
  files: readonly MiniappInventoryInputFile[] = vueTodoFiles,
  sourceLabel: MiniappSourceLabel = "vue3",
  targets?: readonly MiniappPlatform[],
): MiniappConversionExecutionInput {
  return { schemaVersion: "1.0", request: miniappRequest(files, sourceLabel, targets), files };
}
