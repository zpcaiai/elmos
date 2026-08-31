"use client";

import { useMemo, useState } from "react";
import styles from "./ObservabilityWorkspace.module.css";
import { Icon } from "../components/Icon";

interface SpanItem {
  id: string;
  name: string;
  durationMs: number;
  status: "SAMPLE_ONLY";
  attributes: Record<string, string | number | boolean>;
}

const sampleSpans: SpanItem[] = [
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
];

export function ObservabilityWorkspace() {
  const [selectedSpan, setSelectedSpan] = useState<SpanItem>(sampleSpans[2]);
  const [activeTab, setActiveTab] = useState<"traces" | "metrics" | "slsa">("traces");

  const totalDuration = useMemo(
    () => sampleSpans.reduce((sum, s) => sum + s.durationMs, 0),
    [],
  );

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <div className={styles.badge}>SAMPLE DATA · NOT_RUN</div>
          <h1 className={styles.title}>可观测性与供应链证据结构预览</h1>
        </div>
        <p className={styles.subtitle}>
          展示 Trace、Prometheus 与 In-toto/SLSA 字段形态；未读取遥测后端、未执行构建，也未验证任何签名。
        </p>

        <div className={styles.notice} role="status">
          Provider read NOT_RUN · Signature verification NOT_RUN · Independent evidence NOT_RUN · Certification NOT_CERTIFIED
        </div>

        <div className={styles.tabBar}>
          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === "traces" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("traces")}
            aria-pressed={activeTab === "traces"}
          >
            <Icon name="workflow" size={16} />
            Trace 数据示例
          </button>
          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === "metrics" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("metrics")}
            aria-pressed={activeTab === "metrics"}
          >
            <Icon name="test" size={16} />
            Prometheus 指标示例
          </button>

          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === "slsa" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("slsa")}
            aria-pressed={activeTab === "slsa"}
          >
            <Icon name="shield" size={16} />
            SLSA 凭证结构示例
          </button>
        </div>
      </header>

      <div className={styles.mainGrid}>
        {activeTab === "traces" && (
          <>
            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Trace Waterfall 字段示例</h2>
                <span className={styles.metaTag}>SAMPLE_ONLY · {totalDuration.toFixed(1)} ms</span>
              </div>
              <div className={styles.waterfallList}>
                {sampleSpans.map((span) => {
                  const widthPct = Math.max(10, (span.durationMs / totalDuration) * 100);
                  const isSelected = selectedSpan.id === span.id;
                  return (
                    <button
                      type="button"
                      key={span.id}
                      className={`${styles.spanRow} ${isSelected ? styles.spanRowSelected : ""}`}
                      onClick={() => setSelectedSpan(span)}
                      aria-pressed={isSelected}
                    >
                      <div className={styles.spanNameCol}>
                        <span className={styles.statusDot} />
                        <span className={styles.spanName}>{span.name}</span>
                      </div>
                      <div className={styles.spanBarContainer}>
                        <div
                          className={styles.spanBar}
                          style={{ width: `${widthPct}%` }}
                        >
                          {span.durationMs} ms
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Span 示例字段</h2>
                <span className={styles.metaTag}>{selectedSpan.name}</span>
              </div>
              <div className={styles.detailsContent}>
                <div className={styles.kvGrid}>
                  <div className={styles.kvItem}>
                    <span className={styles.kLabel}>Span ID</span>
                    <span className={styles.kValue}>{selectedSpan.id}</span>
                  </div>
                  <div className={styles.kvItem}>
                    <span className={styles.kLabel}>执行状态</span>
                    <span className={styles.kValue}>
                      {selectedSpan.status}
                    </span>
                  </div>
                  <div className={styles.kvItem}>
                    <span className={styles.kLabel}>持续耗时</span>
                    <span className={styles.kValue}>{selectedSpan.durationMs} ms</span>
                  </div>
                </div>

                <h3 className={styles.subHeading}>Attributes (OpenTelemetry Attributes)</h3>
                <pre className={styles.codeBlock}>
                  {JSON.stringify(selectedSpan.attributes, null, 2)}
                </pre>
              </div>
            </div>
          </>
        )}

        {activeTab === "metrics" && (
          <div className={styles.fullPanel}>
            <div className={styles.panelHeader}>
              <h2>Prometheus 指标名称示例</h2>
              <span className={styles.metaTag}>Scrape Status: NOT_RUN</span>
            </div>
            <div className={styles.metricsGrid}>
              <div className={styles.metricCard}>
                <div className={styles.mValue}>—</div>
                <div className={styles.mLabel}>elmos_transformations_total</div>
                <div className={styles.mDesc}>未连接指标端点</div>
              </div>
              <div className={styles.metricCard}>
                <div className={styles.mValue}>—</div>
                <div className={styles.mLabel}>elmos_ast_nodes_parsed_total</div>
                <div className={styles.mDesc}>未连接指标端点</div>
              </div>
              <div className={styles.metricCard}>
                <div className={styles.mValue}>—</div>
                <div className={styles.mLabel}>elmos_proof_obligations_discharged</div>
                <div className={styles.mDesc}>无证明执行或放行证据</div>
              </div>
              <div className={styles.metricCard}>
                <div className={styles.mValue}>—</div>
                <div className={styles.mLabel}>elmos_cas_hit_ratio</div>
                <div className={styles.mDesc}>未连接指标端点</div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "slsa" && (
          <div className={styles.fullPanel}>
            <div className={styles.panelHeader}>
              <h2>In-Toto / SLSA 凭证字段结构示例</h2>
              <span className={styles.metaTag}>Verification: NOT_RUN</span>
            </div>
            <div className={styles.slsaCard}>
              <div className={styles.slsaRow}>
                <strong>Predicate Type:</strong> <code>https://slsa.dev/provenance/v1</code>
              </div>
              <div className={styles.slsaRow}>
                <strong>Builder ID:</strong> <code>NOT_BOUND</code>
              </div>
              <div className={styles.slsaRow}>
                <strong>Signature:</strong> <code>NOT_GENERATED</code>
              </div>
              <div className={styles.slsaRow}>
                <strong>Hermetic Toolchains Locked:</strong> <code>NOT_RUN</code>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
