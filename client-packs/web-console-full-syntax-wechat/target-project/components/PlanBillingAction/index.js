Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    plan: {
      type: null,
      value: null,
    },
    orderable: {
      type: null,
      value: null,
    },
  },
  data: {
    key: null,
    pending: false,
    message: "",
    failed: false,
    qrCode: null,
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
