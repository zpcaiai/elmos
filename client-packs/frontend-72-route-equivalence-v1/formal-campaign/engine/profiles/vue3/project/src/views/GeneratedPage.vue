<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { routes } from "../routes";
const current = useRoute();
const page = computed(() => routes.find(route => route.path === current.path) ?? routes[0]);
</script>
<template><main class="content" id="main" :data-route-id="page?.id" :data-route-path="page?.path" :data-requires-auth="page?.requiresAuth" :data-deep-link="page?.deepLink"><article class="card">
  <h1>{{ page?.title }}</h1><p>{{ page?.text }}</p>
  <p class="status" role="status">生成状态：等待真实浏览器与可访问性验证</p>
</article></main></template>
