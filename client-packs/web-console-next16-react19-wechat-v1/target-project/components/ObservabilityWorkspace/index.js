// Top-level helpers and constants
try { var sampleSpans = [
    {
        id: "span-01",
        name: "elmos.pipeline.cst_parsing",
        durationMs: 4.2,
        status: "SAMPLE_ONLY",
        attributes: { "sample.lang.source": "java", "sample.parser": "tree-sitter", "execution.status": "NOT_RUN" },
    },
    {
        id: "span-02",
        name: "elmos.pipeline.type_algebra",
        durationMs: 6.8,
        status: "SAMPLE_ONLY",
        attributes: { "sample.stage": "type-algebra", "execution.status": "NOT_RUN" },
    },
    {
        id: "span-03",
        name: "elmos.pipeline.smt_verification",
        durationMs: 12.5,
        status: "SAMPLE_ONLY",
        attributes: { "sample.solver": "z3", "verification.status": "NOT_RUN" },
    },
    {
        id: "span-04",
        name: "elmos.pipeline.lean4_proof",
        durationMs: 8.4,
        status: "SAMPLE_ONLY",
        attributes: { "sample.kernel": "lean4", "verification.status": "NOT_RUN" },
    },
    {
        id: "span-05",
        name: "elmos.pipeline.cas_store",
        durationMs: 1.1,
        status: "SAMPLE_ONLY",
        attributes: { "sample.stage": "cas-store", "artifact.status": "NOT_GENERATED" },
    },
]; } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    selectedSpan: "sampleSpans[2]",
    activeTab: "traces",
    totalDuration: null,
  },
  lifetimes: {
    attached() {
      const setSelectedSpan = (val) => { this.setData({ selectedSpan: typeof val === "function" ? val(this.data.selectedSpan) : val }); };
      const setActiveTab = (val) => { this.setData({ activeTab: typeof val === "function" ? val(this.data.activeTab) : val }); };
    },
    detached() {
    },
  },
  methods: {
  },
});
