// Top-level helpers and constants
try { const jobStatuses = [
    ["ALL", "全部状态"],
    ["QUEUED", "排队 QUEUED"],
    ["CLAIMED", "已认领 CLAIMED"],
    ["RUNNING", "执行中 RUNNING"],
    ["SUCCEEDED", "成功 SUCCEEDED"],
    ["PARTIAL", "部分成功 PARTIAL"],
    ["FAILED", "失败 FAILED"],
    ["CANCELLED", "已取消 CANCELLED"],
    ["LOST", "丢失 LOST"],
]; } catch(e) {}
try { function yuan(minor) {
    if (minor === null || minor === undefined)
        return "未计费";
    const value = typeof minor === "number" ? minor : Number(minor);
    if (!Number.isFinite(value))
        return "未计费";
    return (value / 100).toLocaleString("zh-CN", {
        style: "currency",
        currency: "CNY",
        minimumFractionDigits: 2,
    });
} } catch(e) {}
try { function moment(value) {
    if (!value)
        return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString("zh-CN", { hour12: false });
} } catch(e) {}
try { function elapsed(row) {
    if (!row.startedAt)
        return "—";
    const started = new Date(row.startedAt);
    if (Number.isNaN(started.getTime()))
        return "—";
    const end = row.finishedAt ? new Date(row.finishedAt) : new Date();
    if (Number.isNaN(end.getTime()))
        return "—";
    const seconds = Math.max(0, Math.round((end.getTime() - started.getTime()) / 1000));
    return `${seconds}s`;
} } catch(e) {}

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
