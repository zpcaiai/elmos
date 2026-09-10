// Top-level helpers and constants
try { const statusPresentation = {
    PASSED: { label: "已通过", short: "通过", tone: "passed" },
    FAILED: { label: "失败", short: "失败", tone: "failed" },
    BLOCKED: { label: "阻断", short: "阻断", tone: "blocked" },
    NOT_RUN: { label: "未运行", short: "未运行", tone: "not-run" },
    UNKNOWN: { label: "未知", short: "未知", tone: "unknown" },
    NOT_APPLICABLE: { label: "不适用", short: "N/A", tone: "not-applicable" },
    LIMITED: { label: "受限", short: "受限", tone: "limited" },
    REPRESENTED: { label: "已表示", short: "已表示", tone: "represented" },
    DECLARED: { label: "已声明", short: "已声明", tone: "declared" },
}; } catch(e) {}
try { const generationLanguageLabels = {
    java: "Java",
    python: "Python",
    csharp: "C#",
    typescript: "TypeScript",
    go: "Go",
    kotlin: "Kotlin",
    php: "PHP",
    rust: "Rust",
}; } catch(e) {}
try { const segmentOrder = [
    "PASSED",
    "FAILED",
    "BLOCKED",
    "NOT_RUN",
    "UNKNOWN",
    "NOT_APPLICABLE",
]; } catch(e) {}
try { function finiteCount(value) {
    return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
} } catch(e) {}
try { function graphLayers(nodes, edges) {
    const nodeIds = new Set(nodes.map((node) => node.id));
    const depth = new Map(nodes.map((node) => [node.id, 0]));
    for (let pass = 0; pass < nodes.length; pass += 1) {
        let changed = false;
        for (const edge of edges) {
            if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to))
                continue;
            const candidate = Math.min(nodes.length - 1, (depth.get(edge.from) ?? 0) + 1);
            if (candidate > (depth.get(edge.to) ?? 0)) {
                depth.set(edge.to, candidate);
                changed = true;
            }
        }
        if (!changed)
            break;
    }
    const layers = new Map();
    for (const node of nodes) {
        const layer = depth.get(node.id) ?? 0;
        layers.set(layer, [...(layers.get(layer) ?? []), node]);
    }
    return [...layers.entries()]
        .sort(([left], [right]) => left - right)
        .map(([, layerNodes]) => layerNodes.sort((left, right) => left.label.localeCompare(right.label)));
} } catch(e) {}
try { function projectStructureGraph(structure) {
    return {
        nodes: structure.nodes.map((node) => ({
            id: node.id,
            label: node.label,
            kind: node.kind,
            detail: `${node.path} · ${node.file_count} 个文件${node.runtime ? ` · ${node.runtime}` : ""}`,
            status: node.status,
        })),
        edges: structure.edges.map((edge) => ({ ...edge, label: edge.type })),
    };
} } catch(e) {}
try { function fallbackStructureGraph(structure) {
    return {
        nodes: structure.nodes.map((node) => ({
            id: node.id,
            label: node.label,
            kind: node.kind,
            detail: `${node.path}${node.language ? ` · ${generationLanguageLabels[node.language]}` : ""}`,
            status: node.status,
        })),
        edges: structure.edges.map((edge) => ({ ...edge, label: edge.relation })),
    };
} } catch(e) {}
try { function dependencyGraph(graph) {
    return {
        nodes: graph.nodes.map((node) => ({
            id: node.id,
            label: node.coordinate,
            kind: node.kind,
            detail: `版本来源 · ${node.version_source}`,
            status: "DECLARED",
        })),
        edges: graph.edges.map((edge) => ({
            from: edge.from,
            to: edge.to,
            label: `${edge.type} · ${edge.scope} · ${edge.evidence_status}`,
        })),
    };
} } catch(e) {}
try { function matrixLanguages(behavior) {
    const languages = [];
    for (const language of [
        ...behavior.targets.map((target) => target.language),
        ...behavior.cross_target_matrix.flatMap((entry) => [entry.source, entry.target]),
    ]) {
        if (!languages.includes(language))
            languages.push(language);
    }
    return languages;
} } catch(e) {}

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
