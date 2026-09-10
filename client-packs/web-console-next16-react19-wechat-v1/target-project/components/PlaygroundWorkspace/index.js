Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    sourceLang: "java",
    targetLang: "csharp",
    sourceCode: "DEFAULT_JAVA_SNIPPET",
    executionState: "NOT_RUN",
    executionMessage: "当前页面仅展示静态输入、目标与规格示例；尚未连接真实转换、SMT、Lean、SCM 或签名 Runner。",
    activeTab: "code",
    targetCode: null,
  },
  lifetimes: {
    attached() {
      const setSourceLang = (val) => { this.setData({ sourceLang: typeof val === "function" ? val(this.data.sourceLang) : val }); };
      const setTargetLang = (val) => { this.setData({ targetLang: typeof val === "function" ? val(this.data.targetLang) : val }); };
      const setSourceCode = (val) => { this.setData({ sourceCode: typeof val === "function" ? val(this.data.sourceCode) : val }); };
      const setExecutionState = (val) => { this.setData({ executionState: typeof val === "function" ? val(this.data.executionState) : val }); };
      const setExecutionMessage = (val) => { this.setData({ executionMessage: typeof val === "function" ? val(this.data.executionMessage) : val }); };
      const setActiveTab = (val) => { this.setData({ activeTab: typeof val === "function" ? val(this.data.activeTab) : val }); };
    },
    detached() {
    },
  },
  methods: {
  },
});
