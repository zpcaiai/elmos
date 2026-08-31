"use client";

import { useMemo, useState } from "react";
import styles from "./ObservabilityWorkspace.module.css";
import { Icon } from "../components/Icon";

interface SpanItem {
  id: string;
  name: string;
  durationMs: number;
  status: "OK" | "SLOW" | "ERROR";
  attributes: Record<string, string | number | boolean>;
}

const mockSpans: SpanItem[] = [
  {
    id: "span-01",
    name: "elmos.pipeline.cst_parsing",
    durationMs: 4.2,
    status: "OK",
    attributes: { "elmos.lang.source": "java", "elmos.ast.node_count": 142, "elmos.parser": "tree-sitter" },
  },
  {
    id: "span-02",
    name: "elmos.pipeline.type_algebra",
    durationMs: 6.8,
    status: "OK",
    attributes: { "elmos.type.resolved_symbols": 89, "elmos.type.invariants": 14 },
  },
  {
    id: "span-03",
    name: "elmos.pipeline.smt_verification",
    durationMs: 12.5,
    status: "OK",
    attributes: { "elmos.smt.solver": "z3-4.12.2", "elmos.smt.verdict": "UNSAT_PASS", "elmos.smt.time_ms": 11.8 },
  },
  {
    id: "span-04",
    name: "elmos.pipeline.lean4_proof",
    durationMs: 8.4,
    status: "OK",
    attributes: { "elmos.lean.kernel": "4.8.0", "elmos.lean.theorems_generated": 3, "elmos.lean.sorry_free": true },
  },
  {
    id: "span-05",
    name: "elmos.pipeline.cas_store",
    durationMs: 1.1,
    status: "OK",
    attributes: { "elmos.cas.cache_hit": true, "elmos.cas.merkle_root": "7f8b9a1c..." },
  },
];

export function ObservabilityWorkspace() {
  const [selectedSpan, setSelectedSpan] = useState<SpanItem>(mockSpans[2]);
  const [activeTab, setActiveTab] = useState<"traces" | "metrics" | "slsa">("traces");

  const totalDuration = useMemo(
    () => mockSpans.reduce((sum, s) => sum + s.durationMs, 0),
    [],
  );

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <div className={styles.badge}>OTLP v1.3 / SLSA Level 4</div>
          <h1 className={styles.title}>全链路 OpenTelemetry 追踪与 SLSA 凭证仪表盘</h1>
        </div>
        <p className={styles.subtitle}>
          实时监测转换流水线执行 Span 瀑布图、Prometheus 聚合指标与 In-toto / CycloneDX 密码学凭证。
        </p>

        <div className={styles.tabBar}>
          <button
            className={`${styles.tabBtn} ${activeTab === "traces" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("traces")}
          >
            <Icon name="workflow" size={16} />
            分布式 Trace 瀑布图
          </button>
          <button
            className={`${styles.tabBtn} ${activeTab === "metrics" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("metrics")}
          >
            <Icon name="test" size={16} />
            Prometheus 实时指标
          </button>

          <button
            className={`${styles.tabBtn} ${activeTab === "slsa" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("slsa")}
          >
            <Icon name="shield" size={16} />
            SLSA Level 4 密码学凭证
          </button>
        </div>
      </header>

      <div className={styles.mainGrid}>
        {activeTab === "traces" && (
          <>
            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Trace Waterfall (Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736)</h2>
                <span className={styles.metaTag}>耗时: {totalDuration.toFixed(1)} ms</span>
              </div>
              <div className={styles.waterfallList}>
                {mockSpans.map((span) => {
                  const widthPct = Math.max(10, (span.durationMs / totalDuration) * 100);
                  const isSelected = selectedSpan.id === span.id;
                  return (
                    <div
                      key={span.id}
                      className={`${styles.spanRow} ${isSelected ? styles.spanRowSelected : ""}`}
                      onClick={() => setSelectedSpan(span)}
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
                    </div>
                  );
                })}
              </div>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <h2>Span 详情与 W3C 属性</h2>
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
                    <span className={styles.kValue} style={{ color: "var(--accent-green)" }}>
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
              <h2>Prometheus Metrics Endpoint (`elmos telemetry metrics`)</h2>
              <span className={styles.metaTag}>Scrape Status: UP</span>
            </div>
            <div className={styles.metricsGrid}>
              <div className={styles.metricCard}>
                <div className={styles.mValue}>128</div>
                <div className={styles.mLabel}>elmos_transformations_total</div>
                <div className={styles.mDesc}>全库端到端语义转换总数</div>
              </div>
              <div className={styles.metricCard}>
                <div className={styles.mValue}>452,900</div>
                <div className={styles.mLabel}>elmos_ast_nodes_parsed_total</div>
                <div className={styles.mDesc}>Tree-sitter 增量解析节点数</div>
              </div>
              <div className={styles.metricCard}>
                <div className={styles.mValue}>640</div>
                <div className={styles.mLabel}>elmos_proof_obligations_discharged</div>
                <div className={styles.mDesc}>SMT / Lean 4 定理证明放行数</div>
              </div>
              <div className={styles.metricCard}>
                <div className={styles.mValue}>88.4%</div>
                <div className={styles.mLabel}>elmos_cas_hit_ratio</div>
                <div className={styles.mDesc}>内容寻址 Action Cache 命中率</div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "slsa" && (
          <div className={styles.fullPanel}>
            <div className={styles.panelHeader}>
              <h2>In-Toto / SLSA Level 4 密码学构建存证</h2>
              <span className={styles.metaTag}>Ed25519 Verified</span>
            </div>
            <div className={styles.slsaCard}>
              <div className={styles.slsaRow}>
                <strong>Predicate Type:</strong> <code>https://slsa.dev/provenance/v1</code>
              </div>
              <div className={styles.slsaRow}>
                <strong>Builder ID:</strong> <code>https://github.com/zpcaiai/elmos/hermetic-builder@v3.0.0</code>
              </div>
              <div className={styles.slsaRow}>
                <strong>Signature:</strong> <code>3fa89b2c7e014d5f99238910fedcba45... (HMAC-SHA256 / Ed25519)</code>
              </div>
              <div className={styles.slsaRow}>
                <strong>Hermetic Toolchains Locked:</strong> <code>Lean 4.8.0, Dafny 4.4.0, Z3 4.12.2, CVC5 1.1.2</code>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
