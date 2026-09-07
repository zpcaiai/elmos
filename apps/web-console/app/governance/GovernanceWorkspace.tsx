"use client";

import React, { useState } from "react";
import styles from "./GovernanceWorkspace.module.css";
import { Icon } from "../components/Icon";

interface MutantItem {
  id: string;
  operator: string;
  original: string;
  mutated: string;
  line: number;
  status: "KILLED" | "SURVIVED";
}

interface ContractDiffItem {
  endpoint: string;
  category: string;
  severity: "BREAKING" | "WARNING" | "NON_BREAKING";
  description: string;
}

const sampleMutants: MutantItem[] = [
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
];

const sampleDiffs: ContractDiffItem[] = [
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
];

export function GovernanceWorkspace() {
  const [activeTab, setActiveTab] = useState<"mutation" | "api-diff" | "cas-cache">("mutation");
  const [codeSnippet, setCodeSnippet] = useState(
    "public int calculateDiscount(int price) {\n  if (price > 100) {\n    return price - 20;\n  }\n  return price;\n}"
  );
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [mutationResults, setMutationResults] = useState<MutantItem[] | null>(null);
  const [cacheStats, setCacheStats] = useState({
    l1Items: 14,
    totalEntries: 240,
    totalSizeBytes: 3145728,
    hitRatio: 0.8842,
    bloomFilterBits: 2048,
  });

  const handleRunMutation = () => {
    setIsAnalyzing(true);
    setTimeout(() => {
      setMutationResults(sampleMutants);
      setIsAnalyzing(false);
    }, 400);
  };

  const handlePurgeL1 = () => {
    setCacheStats((prev) => ({
      ...prev,
      l1Items: 0,
      hitRatio: 0.821,
    }));
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <span className={styles.badge}>ELMOS Governance & Assurance OS</span>
          <h1 className={styles.title}>契约治理、变异测试与多级缓存中心</h1>
        </div>
        <p className={styles.subtitle}>
          展示变异、API 差分和缓存治理的交互形态；本页面未连接真实 Runner，所有示例均不构成执行证据。
        </p>

        <div className={styles.notice} role="status">
          SAMPLE_ONLY · Runner execution NOT_RUN · Independent verification NOT_RUN · Certification NOT_CERTIFIED
        </div>

        <div className={styles.tabBar}>
          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === "mutation" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("mutation")}
            aria-pressed={activeTab === "mutation"}
          >
            <Icon name="test" size={16} />
            变异测试充分性分析 (Mutation Testing)
          </button>
          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === "api-diff" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("api-diff")}
            aria-pressed={activeTab === "api-diff"}
          >
            <Icon name="route" size={16} />
            API 契约向后兼容漂移差分 (API Diff)
          </button>
          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === "cas-cache" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("cas-cache")}
            aria-pressed={activeTab === "cas-cache"}
          >
            <Icon name="database" size={16} />
            多级 CAS 缓存网络 (CAS Cache & Bloom)
          </button>
        </div>
      </header>

      {activeTab === "mutation" && (
        <div className={styles.mainGrid}>
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <h2>待测业务逻辑 (Source Code)</h2>
              <button type="button" className={styles.runBtn} onClick={handleRunMutation} disabled={isAnalyzing}>
                <Icon name="play" size={14} />
                {isAnalyzing ? "生成示例中..." : "生成变异结果示例（不执行 Runner）"}
              </button>
            </div>
            <textarea
              aria-label="待测业务逻辑示例"
              className={styles.editor}
              value={codeSnippet}
              onChange={(e) => setCodeSnippet(e.target.value)}
              rows={8}
            />

            <div className={styles.scoreBoard} aria-label="变异测试示例状态">
              <div className={styles.scoreItem}>
                <span className={styles.scoreVal}>{mutationResults ? "75.0%" : "NOT_RUN"}</span>
                <span className={styles.scoreLbl}>变异杀伤率 (Kill Score)</span>
              </div>
              <div className={styles.scoreItem}>
                <span className={styles.scoreVal}>{mutationResults ? "3 / 4" : "—"}</span>
                <span className={styles.scoreLbl}>已击杀变异体 (Killed Mutants)</span>
              </div>
              <div className={styles.scoreItem}>
                <span className={styles.scoreVal}>{mutationResults ? "1" : "—"}</span>
                <span className={styles.scoreLbl}>存活变异体 (Survived)</span>
              </div>
            </div>
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <h2>变异体示例 (Illustrative Mutants)</h2>
              <span className={styles.metaTag}>{mutationResults ? "SAMPLE_ONLY" : "NOT_RUN"}</span>
            </div>
            <div className={styles.mutantList}>
              {!mutationResults ? (
                <p className={styles.emptyState}>尚未生成示例；真实变异测试、编译与测试回放均为 NOT_RUN。</p>
              ) : mutationResults.map((m) => (
                <div key={m.id} className={styles.mutantCard}>
                  <div className={styles.mutantHeader}>
                    <span className={styles.mutantId}>{m.id}</span>
                    <span className={styles.mutantOp}>{m.operator}</span>
                    <span
                      className={`${styles.statusBadge} ${
                        m.status === "KILLED" ? styles.statusKilled : styles.statusSurvived
                      }`}
                    >
                      {m.status === "KILLED" ? "✓ KILLED" : "⚠ SURVIVED"}
                    </span>
                  </div>
                  <div className={styles.diffSnippet}>
                    <div className={styles.diffOrig}>- Line {m.line}: {m.original}</div>
                    <div className={styles.diffMut}>+ Line {m.line}: {m.mutated}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === "api-diff" && (
        <div className={styles.fullPanel}>
          <div className={styles.panelHeader}>
            <h2>API 契约差分静态示例</h2>
            <span className={styles.dangerTag}>SAMPLE_ONLY · NOT_RUN</span>
          </div>

          <div className={styles.diffList}>
            {sampleDiffs.map((d, i) => (
              <div key={i} className={styles.diffCard}>
                <div className={styles.diffCardHeader}>
                  <span className={styles.endpointName}>{d.endpoint}</span>
                  <span
                    className={`${styles.sevBadge} ${
                      d.severity === "BREAKING"
                        ? styles.sevBreaking
                        : d.severity === "WARNING"
                        ? styles.sevWarning
                        : styles.sevNonBreaking
                    }`}
                  >
                    {d.severity}
                  </span>
                </div>
                <div className={styles.diffCardBody}>
                  <span className={styles.catLabel}>{d.category}</span>: {d.description}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === "cas-cache" && (
        <div className={styles.fullPanel}>
          <div className={styles.panelHeader}>
            <h2>浏览器内缓存状态示例</h2>
            <button type="button" className={styles.purgeBtn} onClick={handlePurgeL1}>
              <Icon name="refresh" size={14} /> 清空页面示例 L1 状态
            </button>
          </div>

          <div className={styles.metricsGrid}>
            <div className={styles.metricCard}>
              <span className={styles.mValue}>{cacheStats.l1Items}</span>
              <span className={styles.mLabel}>L1 Memory Items</span>
              <span className={styles.mDesc}>高速内存 LRU 缓存条目数</span>
            </div>
            <div className={styles.metricCard}>
              <span className={styles.mValue}>{cacheStats.totalEntries}</span>
              <span className={styles.mLabel}>Total Cached DAG Units</span>
              <span className={styles.mDesc}>多级缓存持久化总单元</span>
            </div>
            <div className={styles.metricCard}>
              <span className={styles.mValue}>{(cacheStats.hitRatio * 100).toFixed(1)}%</span>
              <span className={styles.mLabel}>Cache Hit Ratio</span>
              <span className={styles.mDesc}>CAS 命中加速比</span>
            </div>
            <div className={styles.metricCard}>
              <span className={styles.mValue}>{cacheStats.bloomFilterBits} bits</span>
              <span className={styles.mLabel}>Bloom Filter Active</span>
              <span className={styles.mDesc}>布隆过滤器极速预检</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
