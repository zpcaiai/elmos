import { defineStore } from "pinia";

export const useTodoStore = defineStore("todos", {
  state: () => ({ items: [] as string[] }),
  actions: {
    add(text: string) {
      const value = text.trim();
      if (value) this.items.push(value);
    },
  },
});
