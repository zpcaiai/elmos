<script setup lang="ts">
import { ref } from "vue";
import { useTodoStore } from "../stores/todo";

const text = ref("");
const todos = useTodoStore();

function submit() {
  todos.add(text.value);
  text.value = "";
}
</script>

<template>
  <section>
    <input v-model="text" aria-label="Todo text" />
    <button :disabled="!text.trim()" @click="submit">Add</button>
    <ul>
      <li v-for="(item, index) in todos.items" :key="`${item}-${index}`">{{ item }}</li>
    </ul>
  </section>
</template>
