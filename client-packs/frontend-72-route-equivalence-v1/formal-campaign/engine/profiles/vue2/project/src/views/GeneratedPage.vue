<script>
import { routes } from "../routes";
export default { computed: { page() { return routes.find(route => route.path === this.$route.path) || routes[0]; } } };
</script>
<template><main class="content" id="main" :data-route-id="page && page.id" :data-route-path="page && page.path" :data-requires-auth="page && page.requiresAuth" :data-deep-link="page && page.deepLink"><article class="card">
  <h1>{{ page && page.title }}</h1><p>{{ page && page.text }}</p>
  <p class="status" role="status">生成状态：等待真实浏览器与可访问性验证</p>
</article></main></template>
