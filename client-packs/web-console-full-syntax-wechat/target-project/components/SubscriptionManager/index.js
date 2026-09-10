Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    cancelKey: null,
    subscription: null,
    state: "LOADING",
    confirming: false,
    pending: false,
    message: "",
  },
  lifetimes: {
    attached() {
      const setSubscription = (val) => { this.setData({ subscription: typeof val === "function" ? val(this.data.subscription) : val }); };
      const setState = (val) => { this.setData({ state: typeof val === "function" ? val(this.data.state) : val }); };
      const setConfirming = (val) => { this.setData({ confirming: typeof val === "function" ? val(this.data.confirming) : val }); };
      const setPending = (val) => { this.setData({ pending: typeof val === "function" ? val(this.data.pending) : val }); };
      const setMessage = (val) => { this.setData({ message: typeof val === "function" ? val(this.data.message) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          void load();
    const refresh = () => void load();
    window.addEventListener("elmos:billing-changed", refresh);
    return () => window.removeEventListener("elmos:billing-changed", refresh);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
  },
});
