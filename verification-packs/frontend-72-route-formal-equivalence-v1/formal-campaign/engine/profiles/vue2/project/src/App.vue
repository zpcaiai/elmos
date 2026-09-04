<script>
import { routes } from "./routes";
export default { data: () => ({ routes }) };
</script>
<template><div class="shell"><nav class="nav" aria-label="主要导航">
  <strong>ELMOS 有界导航验证</strong>
  <RouterLink v-for="route in routes" :key="route.id" :to="route.path" :data-route-id="route.id" :data-requires-auth="route.requiresAuth ? 'true' : 'false'" :data-deep-link="route.deepLink ? 'true' : 'false'">{{ route.title }}</RouterLink>
</nav><RouterView /></div></template>
