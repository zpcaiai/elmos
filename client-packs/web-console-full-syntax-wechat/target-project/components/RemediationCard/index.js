Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    proposal: {
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
    onApprove(e) {
      this.triggerEvent("approve", e.detail);
    },
    onReject(e) {
      this.triggerEvent("reject", e.detail);
    },
    onPrepareScm(e) {
      this.triggerEvent("preparescm", e.detail);
    },
  },
});
