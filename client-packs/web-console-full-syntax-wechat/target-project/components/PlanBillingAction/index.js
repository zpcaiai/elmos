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
      const setPending = (val) => { this.setData({ pending: typeof val === "function" ? val(this.data.pending) : val }); };
      const setMessage = (val) => { this.setData({ message: typeof val === "function" ? val(this.data.message) : val }); };
      const setFailed = (val) => { this.setData({ failed: typeof val === "function" ? val(this.data.failed) : val }); };
      const setQrCode = (val) => { this.setData({ qrCode: typeof val === "function" ? val(this.data.qrCode) : val }); };
    },
    detached() {
    },
  },
  methods: {
  },
});
