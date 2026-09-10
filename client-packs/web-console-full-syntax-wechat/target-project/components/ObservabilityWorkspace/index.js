Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    selectedSpan: "sampleSpans[2]",
    activeTab: "traces",
    totalDuration: null,
  },
  lifetimes: {
    attached() {
      const setSelectedSpan = (val) => { this.setData({ selectedSpan: typeof val === "function" ? val(this.data.selectedSpan) : val }); };
      const setActiveTab = (val) => { this.setData({ activeTab: typeof val === "function" ? val(this.data.activeTab) : val }); };
    },
    detached() {
    },
  },
  methods: {
  },
});
