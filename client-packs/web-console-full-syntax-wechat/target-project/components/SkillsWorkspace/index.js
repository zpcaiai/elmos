Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    namespace: "foundry",
    searchQuery: "",
    items: null,
  },
  lifetimes: {
    attached() {
      const setNamespace = (val) => { this.setData({ namespace: typeof val === "function" ? val(this.data.namespace) : val }); };
      const setSearchQuery = (val) => { this.setData({ searchQuery: typeof val === "function" ? val(this.data.searchQuery) : val }); };
    },
    detached() {
    },
  },
  methods: {
  },
});
