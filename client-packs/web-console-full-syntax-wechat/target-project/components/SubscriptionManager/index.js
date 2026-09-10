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
      })();
    },
    detached() {
    },
  },
  methods: {
  },
});
