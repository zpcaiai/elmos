Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    rows: [],
    loaded: false,
    status: "ALL",
    organization: "",
    denial: "",
    busy: false,
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
