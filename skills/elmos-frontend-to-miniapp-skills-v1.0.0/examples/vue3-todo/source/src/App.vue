<script setup lang="ts">
import { RouterView } from 'vue-router';
</script>

<template>
  <main class="app-shell">
    <h1>Todo</h1>
    <RouterView />
  </main>
</template>

<style scoped>
.app-shell { max-width: 640px; margin: 0 auto; padding: 16px; }
</style>
