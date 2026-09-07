<script>
import { routes } from "../routes";
export default { computed: { page() { return routes.find(route => route.path === this.$route.path) || routes[0]; } } };
</script>
<template><main class="content" id="main" data-elmos-active-route="true" data-elmos-active-component="true" :data-elmos-route-id="page && page.id" :data-elmos-route-path="page && page.path" :data-elmos-requires-auth="page && page.requiresAuth ? 'true' : 'false'" :data-elmos-deep-link="page && page.deepLink ? 'true' : 'false'" data-elmos-component-id="interaction.shell" :data-elmos-component-key="page && page.id" :data-route-id="page && page.id" :data-route-path="page && page.path" :data-requires-auth="page && page.requiresAuth ? 'true' : 'false'" :data-deep-link="page && page.deepLink ? 'true' : 'false'"><article class="card">
  <h1>{{ page && page.title }}</h1><p>{{ page && page.text }}</p>
  <p class="status" role="status">生成状态：等待真实浏览器与可访问性验证</p>
</article></main></template>
