Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    payload: "{\n    source: \"REPOSITORY_CONTRACT\",\n    fetchedAt: new Date(0).toISOString(),\n    namespace: \"Product Batch B34-B38\",\n    decisionCeiling: \"READY_FOR_EXTERNAL_GATE_OR_HUMAN_DECISION\",\n    externalExecutionEvidence: \"NOT_RUN\",\n    stages: fallbackStages,\n    note: \"正在读取控制面能力…\",\n  }",
    selected: "B37",
    refreshing: false,
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      (async () => {
        try {
          refresh();
        } catch (err) {
          // Handled mount effect
        }
      })();
    },
    detached() {
    },
  },
  methods: {
    moveStage(event, index) {
      try {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
        return;
    event.preventDefault();
    const last = payload.stages.length - 1;
    const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? last : event.key === "ArrowRight" ? (index + 1) % payload.stages.length : (index - 1 + payload.stages.length) % payload.stages.length;
    const nextStage = payload.stages[nextIndex];
    setSelected(nextStage.batch);
    requestAnimationFrame(() => document.getElementById(`trust-tab-${nextStage.batch}`)?.focus());
      } catch (err) {
        console.warn("moveStage execution warning:", err);
      }
    },
  },
});
