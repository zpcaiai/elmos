// Top-level helpers and constants
try { var projectRefPattern = /^[a-z0-9][a-z0-9._/-]{2,180}$/i; } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    draft: "",
    projectRef: null,
  },
  lifetimes: {
    attached() {
      const setDraft = (val) => { this.setData({ draft: typeof val === "function" ? val(this.data.draft) : val }); };
      const setProjectRef = (val) => { this.setData({ projectRef: typeof val === "function" ? val(this.data.projectRef) : val }); };
    },
    detached() {
    },
  },
  methods: {
  },
});
