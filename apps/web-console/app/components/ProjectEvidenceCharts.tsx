import type {
  EvidenceChartStatus,
  GenerationBehaviorInsight,
  GenerationDeclaredDependencyGraph,
  GenerationInsightGraph,
  GenerationInsights,
  GenerationProjectStructure,
  GenerationTargetId,
  TranslationBehaviorCoverage,
  TranslationSemanticCoverage,
} from "../lib/contracts";

const statusPresentation = {
  PASSED: { label: "已通过", short: "通过", tone: "passed" },
  FAILED: { label: "失败", short: "失败", tone: "failed" },
  BLOCKED: { label: "阻断", short: "阻断", tone: "blocked" },
  NOT_RUN: { label: "未运行", short: "未运行", tone: "not-run" },
  UNKNOWN: { label: "未知", short: "未知", tone: "unknown" },
  NOT_APPLICABLE: { label: "不适用", short: "N/A", tone: "not-applicable" },
  LIMITED: { label: "受限", short: "受限", tone: "limited" },
  REPRESENTED: { label: "已表示", short: "已表示", tone: "represented" },
  DECLARED: { label: "已声明", short: "已声明", tone: "declared" },
} as const;

type DisplayStatus = keyof typeof statusPresentation;
type StatusCounts = Partial<Record<DisplayStatus, number>>;

const generationLanguageLabels: Record<GenerationTargetId, string> = {
  java: "Java",
  python: "Python",
  csharp: "C#",
  typescript: "TypeScript",
  go: "Go",
  kotlin: "Kotlin",
  php: "PHP",
  rust: "Rust",
};

const segmentOrder: DisplayStatus[] = [
  "PASSED",
  "FAILED",
  "BLOCKED",
  "NOT_RUN",
  "UNKNOWN",
  "NOT_APPLICABLE",
];

function finiteCount(value: number): number {
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}

function StatusMark({ status, compact = false }: { status: DisplayStatus; compact?: boolean }) {
  const presentation = statusPresentation[status];
  return (
    <span className={`evidence-status evidence-status-${presentation.tone}${compact ? " compact" : ""}`}>
      <span aria-hidden="true" className="evidence-status-dot" />
      {compact ? presentation.short : presentation.label}
    </span>
  );
}

function CoverageMeter({
  label,
  status,
  passed,
  total,
  counts,
}: {
  label: string;
  status: DisplayStatus;
  passed: number;
  total: number;
  counts?: StatusCounts;
}) {
  const safeTotal = finiteCount(total);
  const safePassed = Math.min(finiteCount(passed), safeTotal);
  const inferredRemainderStatus: DisplayStatus = status === "PASSED" && safePassed < safeTotal
    ? "UNKNOWN"
    : status;
  const effectiveCounts: StatusCounts = counts ?? {
    PASSED: safePassed,
    [inferredRemainderStatus]: Math.max(0, safeTotal - safePassed),
  };
  const segments = segmentOrder
    .map((segmentStatus) => ({
      status: segmentStatus,
      count: finiteCount(effectiveCounts[segmentStatus] ?? 0),
    }))
    .filter((segment) => segment.count > 0);
  const valueText = safeTotal > 0
    ? `${safePassed} / ${safeTotal}；${segments.map((segment) => `${statusPresentation[segment.status].label} ${segment.count}`).join("；")}`
    : "0 / 0；当前没有可执行义务";

  return (
    <div className="evidence-meter">
      <div className="evidence-meter-heading">
        <strong>{label}</strong>
        <span>{safePassed} / {safeTotal}</span>
        <StatusMark status={status} compact />
      </div>
      <div
        className="evidence-meter-track"
        role={safeTotal > 0 ? "progressbar" : "status"}
        aria-label={`${label}，${valueText}`}
        aria-valuemin={0}
        aria-valuemax={safeTotal}
        aria-valuenow={safePassed}
        aria-valuetext={valueText}
      >
        {segments.map((segment) => (
          <span
            aria-hidden="true"
            className={`evidence-meter-segment evidence-segment-${statusPresentation[segment.status].tone}`}
            key={segment.status}
            style={{ width: `${safeTotal > 0 ? Math.min(100, segment.count / safeTotal * 100) : 0}%` }}
          />
        ))}
      </div>
      <ul className="evidence-meter-legend" aria-label={`${label}状态明细`}>
        {segments.map((segment) => (
          <li key={segment.status}>
            <span aria-hidden="true" className={`evidence-legend-dot evidence-segment-${statusPresentation[segment.status].tone}`} />
            {statusPresentation[segment.status].label} <strong>{segment.count}</strong>
          </li>
        ))}
        {segments.length === 0 && <li><StatusMark status="NOT_RUN" compact /> 0</li>}
      </ul>
    </div>
  );
}

type DisplayGraphNode = {
  id: string;
  label: string;
  kind: string;
  detail: string;
  status: DisplayStatus;
};

type DisplayGraphEdge = {
  from: string;
  to: string;
  label: string;
};

function graphLayers(nodes: DisplayGraphNode[], edges: DisplayGraphEdge[]): DisplayGraphNode[][] {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const depth = new Map(nodes.map((node) => [node.id, 0]));
  for (let pass = 0; pass < nodes.length; pass += 1) {
    let changed = false;
    for (const edge of edges) {
      if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) continue;
      const candidate = Math.min(nodes.length - 1, (depth.get(edge.from) ?? 0) + 1);
      if (candidate > (depth.get(edge.to) ?? 0)) {
        depth.set(edge.to, candidate);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const layers = new Map<number, DisplayGraphNode[]>();
  for (const node of nodes) {
    const layer = depth.get(node.id) ?? 0;
    layers.set(layer, [...(layers.get(layer) ?? []), node]);
  }
  return [...layers.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, layerNodes]) => layerNodes.sort((left, right) => left.label.localeCompare(right.label)));
}

function EvidenceGraph({
  title,
  description,
  nodes,
  edges,
  status,
}: {
  title: string;
  description: string;
  nodes: DisplayGraphNode[];
  edges: DisplayGraphEdge[];
  status: DisplayStatus;
}) {
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const layers = graphLayers(nodes, edges);
  return (
    <figure className="evidence-graph-card">
      <figcaption>
        <span><strong>{title}</strong><small>{description}</small></span>
        <StatusMark status={status} compact />
      </figcaption>
      {nodes.length === 0 ? (
        <EmptyEvidence title={`${title}尚无数据`} detail="服务端未返回经过校验的结构化图；不会从文件名或日志推断关系。" />
      ) : (
        <ol className="evidence-graph-layers" aria-label={`${title}节点，共 ${nodes.length} 个，可横向滚动`} tabIndex={0}>
          {layers.map((layer, index) => (
            <li className="evidence-graph-layer" key={`${title}-layer-${index}`}>
              <span className="evidence-layer-label">层级 {index + 1}</span>
              <ul>
                {layer.map((node) => (
                  <li className="evidence-graph-node" key={node.id}>
                    <span className="evidence-node-kind">{node.kind}</span>
                    <strong>{node.label}</strong>
                    <small>{node.detail}</small>
                    <StatusMark status={node.status} compact />
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
      {edges.length > 0 && (
        <details className="evidence-edge-details">
          <summary>查看全部关系 · {edges.length}</summary>
          <ul>
            {edges.map((edge, index) => (
              <li key={`${edge.from}-${edge.to}-${edge.label}-${index}`}>
                <span>{nodesById.get(edge.from)?.label ?? edge.from}</span>
                <b aria-label={edge.label}>→</b>
                <span>{nodesById.get(edge.to)?.label ?? edge.to}</span>
                <small>{edge.label}</small>
              </li>
            ))}
          </ul>
        </details>
      )}
    </figure>
  );
}

function EmptyEvidence({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="evidence-empty" role="status">
      <StatusMark status="NOT_RUN" compact />
      <span><strong>{title}</strong><small>{detail}</small></span>
    </div>
  );
}

function projectStructureGraph(structure: GenerationProjectStructure): {
  nodes: DisplayGraphNode[];
  edges: DisplayGraphEdge[];
} {
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
}

function fallbackStructureGraph(structure: GenerationInsightGraph): {
  nodes: DisplayGraphNode[];
  edges: DisplayGraphEdge[];
} {
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
}

function dependencyGraph(graph: GenerationDeclaredDependencyGraph): {
  nodes: DisplayGraphNode[];
  edges: DisplayGraphEdge[];
} {
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
}

function SemanticMappingChart({ semantic }: { semantic: GenerationInsights["semantic"] }) {
  return (
    <section className="evidence-dimension" aria-labelledby="generation-semantic-title">
      <div className="evidence-section-heading">
        <span><h5 id="generation-semantic-title">语义映射</h5><small>映射覆盖与直接语义等价是两个独立维度</small></span>
        <span className="evidence-heading-statuses">
          <StatusMark status={semantic.mapping_status} compact />
          <StatusMark status={semantic.equivalence_status} compact />
        </span>
      </div>
      <CoverageMeter
        label="需求主题映射"
        status={semantic.mapping_status}
        passed={semantic.mapped_subject_count}
        total={semantic.source_subject_count}
      />
      <div className="evidence-subject-grid">
        {semantic.subjects.map((subject) => (
          <article key={subject.id}>
            <div><strong>{subject.label}</strong><StatusMark status={subject.semantic_equivalence_status} compact /></div>
            <CoverageMeter
              label={`${subject.label}映射`}
              status={subject.mapping_status}
              passed={subject.mapped_count}
              total={subject.source_count}
            />
          </article>
        ))}
      </div>
      <ul className="evidence-limitations" aria-label="语义证据限制">
        {semantic.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
      </ul>
    </section>
  );
}

function matrixLanguages(behavior: GenerationBehaviorInsight): GenerationTargetId[] {
  const languages: GenerationTargetId[] = [];
  for (const language of [
    ...behavior.targets.map((target) => target.language),
    ...behavior.cross_target_matrix.flatMap((entry) => [entry.source, entry.target]),
  ]) {
    if (!languages.includes(language)) languages.push(language);
  }
  return languages;
}

function EquivalenceMatrix({
  behavior,
  dimension,
}: {
  behavior: GenerationBehaviorInsight;
  dimension: "semantic" | "behavior";
}) {
  const languages = matrixLanguages(behavior);
  const entries = new Map(behavior.cross_target_matrix.map((entry) => [`${entry.source}>${entry.target}`, entry]));
  const statusKey = dimension === "semantic" ? "semantic_status" : "behavior_status";
  const label = dimension === "semantic" ? "直接语义等价" : "直接行为等价";
  const expectedEligible = languages.length * Math.max(0, languages.length - 1);
  const counts: StatusCounts = {};
  for (const source of languages) {
    for (const target of languages) {
      if (source === target) continue;
      const status = entries.get(`${source}>${target}`)?.[statusKey] ?? "UNKNOWN";
      counts[status] = finiteCount(counts[status] ?? 0) + 1;
    }
  }

  return (
    <details className="evidence-matrix-panel" open>
      <summary>{label} NxN · {finiteCount(counts.PASSED ?? 0)} / {expectedEligible}</summary>
      <CoverageMeter
        label={`${label}有向目标对`}
        status={finiteCount(counts.FAILED ?? 0) > 0 ? "FAILED" : finiteCount(counts.PASSED ?? 0) === expectedEligible && expectedEligible > 0 ? "PASSED" : "NOT_RUN"}
        passed={finiteCount(counts.PASSED ?? 0)}
        total={expectedEligible}
        counts={counts}
      />
      {languages.length === 0 ? (
        <EmptyEvidence title={`${label}矩阵尚无数据`} detail="没有可验证的目标语言集合。" />
      ) : (
        <div className="evidence-matrix-scroll" tabIndex={0} role="region" aria-label={`${label}矩阵，可横向滚动`}>
          <table className="evidence-matrix">
            <caption className="sr-only">{label} NxN 状态矩阵，共 {languages.length} 个目标语言</caption>
            <thead>
              <tr><th scope="col">源 \ 目标</th>{languages.map((language) => <th scope="col" key={language}>{generationLanguageLabels[language]}</th>)}</tr>
            </thead>
            <tbody>
              {languages.map((source) => (
                <tr key={source}>
                  <th scope="row">{generationLanguageLabels[source]}</th>
                  {languages.map((target) => {
                    const entry = entries.get(`${source}>${target}`);
                    const status: EvidenceChartStatus = entry?.[statusKey]
                      ?? (source === target ? "NOT_APPLICABLE" : "UNKNOWN");
                    const reason = entry?.reason ?? (source === target ? "SAME_TARGET" : "MATRIX_CELL_MISSING");
                    return (
                      <td key={target}>
                        <span
                          className={`evidence-matrix-status evidence-status-${statusPresentation[status].tone}`}
                          aria-label={`${generationLanguageLabels[source]} 到 ${generationLanguageLabels[target]}，${label}${statusPresentation[status].label}，${reason}`}
                          title={reason}
                        >
                          {statusPresentation[status].short}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

function BehaviorChart({ behavior }: { behavior: GenerationBehaviorInsight }) {
  return (
    <section className="evidence-dimension" aria-labelledby="generation-behavior-title">
      <div className="evidence-section-heading">
        <span><h5 id="generation-behavior-title">本地行为验证与跨目标等价</h5><small>单目标原生检查通过不会自动提升 NxN 等价状态</small></span>
        <StatusMark status={behavior.status} compact />
      </div>
      <div className="evidence-target-grid">
        {behavior.targets.map((target) => (
          <article key={target.language}>
            <div><strong>{generationLanguageLabels[target.language]}</strong><StatusMark status={target.status} compact /></div>
            <dl>
              <div><dt>精确工具链</dt><dd><StatusMark status={target.exact_toolchain_status} compact /></dd></div>
              <div><dt>构建 / 测试</dt><dd>{target.build_analysis.total}</dd></div>
              <div><dt>启动探针</dt><dd><StatusMark status={target.startup_status} compact /></dd></div>
            </dl>
          </article>
        ))}
        {behavior.targets.length === 0 && <EmptyEvidence title="目标验证尚无数据" detail="没有目标语言验证结果。" />}
      </div>
      <div className="evidence-matrix-pair">
        <EquivalenceMatrix behavior={behavior} dimension="semantic" />
        <EquivalenceMatrix behavior={behavior} dimension="behavior" />
      </div>
      <ul className="evidence-limitations" aria-label="行为证据限制">
        {behavior.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
      </ul>
    </section>
  );
}

export function ProjectEvidenceCharts({ insights }: { insights?: GenerationInsights }) {
  if (!insights) {
    return (
      <section className="project-evidence-charts" aria-labelledby="project-evidence-title">
        <div className="evidence-section-heading">
          <span><h4 id="project-evidence-title">项目结构与等价证据</h4><small>结果数据缺失时保持失败关闭</small></span>
          <StatusMark status="NOT_RUN" compact />
        </div>
        <EmptyEvidence title="项目洞察尚未生成" detail="结构、依赖、语义映射和行为等价均保持 NOT_RUN。" />
      </section>
    );
  }

  const preferredStructure = insights.project_structure
    ? projectStructureGraph(insights.project_structure)
    : fallbackStructureGraph(insights.structure);
  const dependencies = insights.declared_dependencies
    ? dependencyGraph(insights.declared_dependencies)
    : null;
  const structureStatus: DisplayStatus = insights.project_structure?.coverage.status
    ?? (insights.structure.nodes.every((node) => node.status === "PASSED") ? "PASSED" : "NOT_RUN");

  return (
    <section className="project-evidence-charts" aria-labelledby="project-evidence-title">
      <div className="evidence-section-heading">
        <span><h4 id="project-evidence-title">项目结构与等价证据</h4><small>{insights.stage} · 结论上限 {insights.claim_ceiling}</small></span>
        <span className="evidence-heading-statuses"><StatusMark status={structureStatus} compact /><StatusMark status={insights.certification_status === "NOT_CERTIFIED" ? "NOT_RUN" : "UNKNOWN"} compact /></span>
      </div>

      <div className="evidence-graph-grid">
        <EvidenceGraph
          title={insights.project_structure ? "完整项目结构" : "生成流程结构（兼容视图）"}
          description={insights.project_structure
            ? `${insights.project_structure.coverage.classified_file_count} / ${insights.project_structure.coverage.managed_file_count} 个托管文件已分类`
            : `${insights.structure.node_count} 个节点 · ${insights.structure.edge_count} 条关系`}
          nodes={preferredStructure.nodes}
          edges={preferredStructure.edges}
          status={structureStatus}
        />
        {dependencies ? (
          <EvidenceGraph
            title="声明依赖图"
            description={`${dependencies.nodes.length} 个坐标 · ${dependencies.edges.length} 条声明关系 · 完整解析 ${insights.declared_dependencies?.complete ? "是" : "否"}`}
            nodes={dependencies.nodes}
            edges={dependencies.edges}
            status={insights.declared_dependencies?.resolution.status ?? "NOT_RUN"}
          />
        ) : (
          <figure className="evidence-graph-card">
            <figcaption><span><strong>声明依赖图</strong><small>仅接受服务端校验后的声明依赖</small></span><StatusMark status="NOT_RUN" compact /></figcaption>
            <EmptyEvidence title="声明依赖尚未返回" detail="不会从 package 文件名或构建日志推断依赖完整性。" />
          </figure>
        )}
      </div>

      <section className="evidence-dimension" aria-labelledby="generation-coverage-title">
        <div className="evidence-section-heading"><span><h5 id="generation-coverage-title">多维完成度</h5><small>每个维度使用独立且精确的分母</small></span></div>
        <div className="evidence-coverage-grid">
          {insights.coverage.map((dimension) => (
            <CoverageMeter
              key={dimension.id}
              label={dimension.label}
              status={dimension.status}
              passed={dimension.passed}
              total={dimension.total}
            />
          ))}
        </div>
      </section>

      <SemanticMappingChart semantic={insights.semantic} />
      <BehaviorChart behavior={insights.behavior} />
      <div className="evidence-boundary" role="note">
        <strong>证据边界</strong>
        <span>外部验证 {insights.external_verification_status} · 认证 {insights.certification_status}</span>
      </div>
    </section>
  );
}

export function TranslationEvidenceCharts({
  semanticCoverage,
  behaviorCoverage,
}: {
  semanticCoverage?: TranslationSemanticCoverage;
  behaviorCoverage?: TranslationBehaviorCoverage;
}) {
  return (
    <section className="translation-evidence-charts" aria-labelledby="translation-evidence-title">
      <div className="evidence-section-heading">
        <span><h3 id="translation-evidence-title">转换语义与行为覆盖</h3><small>编译器语义主题和行为用例使用不同分母</small></span>
        <StatusMark status={semanticCoverage != null || behaviorCoverage != null ? "REPRESENTED" : "NOT_RUN"} compact />
      </div>
      <div className="translation-coverage-grid">
        <article className="translation-coverage-card">
          <div className="evidence-section-heading">
            <span><h4>Semantic coverage</h4><small>{semanticCoverage?.profile ?? "compiler-semantic-symbol-coverage-v1"}</small></span>
            <StatusMark status={semanticCoverage?.status ?? "NOT_RUN"} compact />
          </div>
          {semanticCoverage != null ? (
            <>
              <CoverageMeter
                label="编译器语义主题"
                status={semanticCoverage.complete ? "PASSED" : semanticCoverage.status}
                passed={semanticCoverage.statusCounts.PASSED}
                total={semanticCoverage.subjectCount}
                counts={semanticCoverage.statusCounts}
              />
              <dl className="evidence-facts">
                <div><dt>源语言</dt><dd>{semanticCoverage.sourceLanguage}</dd></div>
                <div><dt>语义清单</dt><dd><StatusMark status={semanticCoverage.inventoryStatus} compact /></dd></div>
                <div><dt>完整</dt><dd>{semanticCoverage.complete ? "YES" : "NO"}</dd></div>
                <div><dt>主题分母</dt><dd>{semanticCoverage.subjectCount}</dd></div>
              </dl>
            </>
          ) : <EmptyEvidence title="语义覆盖尚未返回" detail="任务状态不会替代逐主题 semanticCoverage。" />}
        </article>

        <article className="translation-coverage-card">
          <div className="evidence-section-heading">
            <span><h4>Behavior coverage</h4><small>{behaviorCoverage?.profile ?? "typed-pure-function-v1"}</small></span>
            <StatusMark status={behaviorCoverage?.status ?? "NOT_RUN"} compact />
          </div>
          {behaviorCoverage != null ? (
            <>
              <CoverageMeter
                label="工作单元行为回放"
                status={behaviorCoverage.complete ? "PASSED" : behaviorCoverage.status}
                passed={behaviorCoverage.statusCounts.PASSED}
                total={behaviorCoverage.workUnitCount}
                counts={behaviorCoverage.statusCounts}
              />
              <dl className="evidence-facts">
                <div><dt>行为用例</dt><dd>{behaviorCoverage.behaviorCaseCount} · {behaviorCoverage.behaviorCaseCountScope}</dd></div>
                <div><dt>已核算工作单元</dt><dd>{behaviorCoverage.accountedWorkUnitCount} / {behaviorCoverage.workUnitCount}</dd></div>
                <div><dt>已尝试 / 未解析</dt><dd>{behaviorCoverage.attemptedWorkUnitCount} / {behaviorCoverage.unresolvedWorkUnitCount}</dd></div>
                <div><dt>完整</dt><dd>{behaviorCoverage.complete ? "YES" : "NO"}</dd></div>
                <div><dt>独立验证</dt><dd><StatusMark status={behaviorCoverage.independentVerificationStatus} compact /></dd></div>
                <div><dt>外部验证</dt><dd><StatusMark status={behaviorCoverage.externalVerificationStatus} compact /></dd></div>
              </dl>
            </>
          ) : <EmptyEvidence title="行为覆盖尚未返回" detail="任务完成不会替代逐工作单元 behaviorCoverage。" />}
        </article>
      </div>
    </section>
  );
}
