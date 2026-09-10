// Top-level helpers and constants
try { function hardware(cpu, memoryGb, diskGb) {
    return `${cpu} vCPU · ${memoryGb} GB RAM · ${diskGb} GB 磁盘`;
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    guidance: {
      type: null,
      value: null,
    },
    selectedTargets: {
      type: null,
      value: null,
    },
    id: {
      type: null,
      value: null,
    },
  },
  data: {
  },
  lifetimes: {
    attached() {
    },
    detached() {
    },
  },
  methods: {
  },
});
