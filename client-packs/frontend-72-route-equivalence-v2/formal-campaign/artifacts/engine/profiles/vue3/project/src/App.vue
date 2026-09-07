<script setup lang="ts">import { routes } from "./routes"; import ElmosInteractionPanel from "./ElmosInteractionPanel.vue";</script>
<template><div class="shell"><nav class="nav" aria-label="主要导航">
  <strong>ELMOS 有界前端交互验证</strong>
  <RouterLink v-for="route in routes" :key="route.id" :to="route.path" :data-route-id="route.id" :data-requires-auth="route.requiresAuth" :data-deep-link="route.deepLink">{{ route.title }}</RouterLink>
</nav><RouterView /><ElmosInteractionPanel /></div></template>
