Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    label: {
      type: null,
      value: null,
    },
    status: {
      type: null,
      value: null,
    },
    passed: {
      type: null,
      value: null,
    },
    total: {
      type: null,
      value: null,
    },
    counts: {
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
