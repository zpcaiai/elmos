// Top-level helpers and constants
try { const sampleMutants = [
    {
        id: "MUT-001",
        operator: "CONDITION_NEGATION",
        original: "if (price > 100)",
        mutated: "if (price <= 100)",
        line: 14,
        status: "KILLED",
    },
    {
        id: "MUT-002",
        operator: "ARITHMETIC_SWAP",
        original: "return price - 20;",
        mutated: "return price + 20;",
        line: 15,
        status: "KILLED",
    },
    {
        id: "MUT-003",
        operator: "RETURN_VALUE_TAMPER",
        original: "return price;",
        mutated: "return 0;",
        line: 16,
        status: "KILLED",
    },
    {
        id: "MUT-004",
        operator: "BOUNDARY_OFF_BY_ONE",
        original: "int maxRetry = 3;",
        mutated: "int maxRetry = 2;",
        line: 28,
        status: "SURVIVED",
    },
]; } catch(e) {}
try { const sampleDiffs = [
    {
        endpoint: "POST /api/v1/orders",
        category: "FIELD_REMOVED",
        severity: "WARNING",
        description: "Request field 'currency' optional in source was removed in target DTO",
    },
    {
        endpoint: "POST /api/v1/orders",
        category: "FIELD_ADDED",
        severity: "NON_BREAKING",
        description: "Response field 'transaction_hash' added with backward-compatible defaults",
    },
    {
        endpoint: "GET /api/v1/payments/{id}",
        category: "TYPE_NARROWING",
        severity: "BREAKING",
        description: "Response field 'amount' narrowed from float64 to int32, risking truncation",
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
    activeTab: "mutation",
    codeSnippet: "public int calculateDiscount(int price) {\n  if (price > 100) {\n    return price - 20;\n  }\n  return price;\n}",
    isAnalyzing: false,
    mutationResults: null,
    cacheStats: "{\n    l1Items: 14,\n    totalEntries: 240,\n    totalSizeBytes: 3145728,\n    hitRatio: 0.8842,\n    bloomFilterBits: 2048,\n  }",
  },
  lifetimes: {
    attached() {
      const setActiveTab = (val) => { this.setData({ activeTab: typeof val === "function" ? val(this.data.activeTab) : val }); };
      const setCodeSnippet = (val) => { this.setData({ codeSnippet: typeof val === "function" ? val(this.data.codeSnippet) : val }); };
      const setIsAnalyzing = (val) => { this.setData({ isAnalyzing: typeof val === "function" ? val(this.data.isAnalyzing) : val }); };
      const setMutationResults = (val) => { this.setData({ mutationResults: typeof val === "function" ? val(this.data.mutationResults) : val }); };
      const setCacheStats = (val) => { this.setData({ cacheStats: typeof val === "function" ? val(this.data.cacheStats) : val }); };
    },
    detached() {
    },
  },
  methods: {
  },
});
