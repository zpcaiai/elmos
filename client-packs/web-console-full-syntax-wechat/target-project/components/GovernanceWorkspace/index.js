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
    },
    detached() {
    },
  },
  methods: {
  },
});
