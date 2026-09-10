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
      const setRows = (val) => { this.setData({ rows: typeof val === "function" ? val(this.data.rows) : val }); };
      const setLoaded = (val) => { this.setData({ loaded: typeof val === "function" ? val(this.data.loaded) : val }); };
      const setStatus = (val) => { this.setData({ status: typeof val === "function" ? val(this.data.status) : val }); };
      const setOrganization = (val) => { this.setData({ organization: typeof val === "function" ? val(this.data.organization) : val }); };
      const setDenial = (val) => { this.setData({ denial: typeof val === "function" ? val(this.data.denial) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
    },
    detached() {
    },
  },
  methods: {
  },
});
