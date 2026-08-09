"use client";

import { useCallback, useEffect, useState } from "react";

type Migration = {
  migrationId: string;
  sourceRepository: string;
  sourceLanguage: string;
  targetLanguage: string;
  targetFramework: string;
  status: string;
  currentPhase: string;
};

type Overview = {
  projects: number;
  migrations: number;
  queuedTasks: number;
  onlineRunners: number;
  recentMigrations: Migration[];
};

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

export default function Home() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [message, setMessage] = useState("正在连接控制面…");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API}/api/v1/overview`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setOverview(await response.json());
      setMessage("控制面已连接");
    } catch (error) {
      setMessage(`控制面暂不可用：${String(error)}`);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  }, [load]);

  async function bootstrapDemo() {
    setBusy(true);
    try {
      const response = await fetch(`${API}/api/v1/demo/bootstrap`, { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      setMessage(`已创建迁移 ${result.migrationId}，Runner 将自动领取任务。`);
      await load();
    } catch (error) {
      setMessage(`创建Demo失败：${String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  const cards = [
    ["项目", overview?.projects ?? "—"],
    ["迁移", overview?.migrations ?? "—"],
    ["排队任务", overview?.queuedTasks ?? "—"],
    ["在线Runner", overview?.onlineRunners ?? "—"],
  ];

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">Batch 20 · Executable Scaffold</p>
          <h1>Migration Platform</h1>
          <p className="subtitle">控制面、Agent服务、Private Runner与事件契约的首个可运行闭环。</p>
        </div>
        <button onClick={bootstrapDemo} disabled={busy}>
          {busy ? "创建中…" : "创建Demo迁移"}
        </button>
      </header>

      <section className="status">{message}</section>

      <section className="cards">
        {cards.map(([label, value]) => (
          <article key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </section>

      <section className="panel">
        <div className="panelHeader">
          <h2>最近迁移</h2>
          <span>每3秒刷新</span>
        </div>
        {!overview?.recentMigrations.length ? (
          <p className="empty">尚无迁移。创建Demo后，Go Runner会领取并完成任务。</p>
        ) : (
          <div className="table">
            {overview.recentMigrations.map((migration) => (
              <div className="row" key={migration.migrationId}>
                <div>
                  <strong>{migration.sourceRepository}</strong>
                  <small>{migration.migrationId}</small>
                </div>
                <div>{migration.sourceLanguage} → {migration.targetLanguage}</div>
                <div>{migration.targetFramework}</div>
                <div><span className="pill">{migration.currentPhase}</span></div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
