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
