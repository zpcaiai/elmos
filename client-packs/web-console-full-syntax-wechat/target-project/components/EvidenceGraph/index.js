Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
    title: {
      type: null,
      value: null,
    },
    description: {
      type: null,
      value: null,
    },
    nodes: {
      type: null,
      value: null,
    },
    edges: {
      type: null,
      value: null,
    },
    status: {
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
