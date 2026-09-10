Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    incident: {
      type: null,
      value: null,
    },
    businessLineLabel: {
      type: null,
      value: null,
    },
    disabled: {
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
    onAssign(e) {
      this.triggerEvent("assign", e.detail);
    },
    onResolve(e) {
      this.triggerEvent("resolve", e.detail);
    },
  },
});
