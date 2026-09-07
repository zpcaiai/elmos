"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import styles from "./LiveWorkbenchStudio.module.css";

type SessionState = "PREPARING" | "READY" | "EXPIRED" | "TERMINATED" | "CLEANUP_PENDING" | "CLEANED" | "QUARANTINED" | "FAILED";
type WorkbenchSession = {
  session: {
    sessionId: string;
    deliveryId: string;
    repositoryId: string;
    snapshotId: string;
    runtimeProfileId: string;
    scenario: string;
    mode: string;
    generation: number;
    state: SessionState;
    runtimeStatus: string;
    version: number;
    expiresAtEpochSecond: number | null;
    evidenceRefs: string[];
  };
  serverNowEpochSecond: number;
  remainingSeconds: number;
  schemaVersion: "lw.v1";
};
type RuntimeEvent = {
  eventId: string;
  sequence: number;
  stopEpoch: number;
  kind: string;
  payloadDigest: string;
  redactionStatus: string;
  serverTimeEpochSecond: number;
};

const terminal = new Set<SessionState>(["EXPIRED", "TERMINATED", "CLEANED", "QUARANTINED", "FAILED"]);
const digestPattern = /^sha256:[a-f0-9]{64}$/;

async function readJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({ code: "INVALID_SERVER_RESPONSE" }));
  if (!response.ok) throw new Error(typeof body.code === "string" ? body.code : `HTTP_${response.status}`);
  return body as T;
}

async function digest(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return `sha256:${Array.from(new Uint8Array(bytes), (part) => part.toString(16).padStart(2, "0")).join("")}`;
}

function formatRemaining(seconds: number): string {
  const bounded = Math.max(0, seconds);
  return `${Math.floor(bounded / 60).toString().padStart(2, "0")}:${(bounded % 60).toString().padStart(2, "0")}`;
}

export function LiveWorkbenchStudio() {
  const [deliveryId, setDeliveryId] = useState("");
  const [repositoryId, setRepositoryId] = useState("");
  const [snapshotId, setSnapshotId] = useState("");
  const [runtimeProfileId, setRuntimeProfileId] = useState("node-ts-linux");
  const [scenario, setScenario] = useState("business-smoke");
  const [mode, setMode] = useState("debug");
  const [session, setSession] = useState<WorkbenchSession | null>(null);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [anchorId, setAnchorId] = useState("");
  const [missionId, setMissionId] = useState("");
  const [correspondenceId, setCorrespondenceId] = useState("");
  const [answers, setAnswers] = useState("");
  const [evidenceView, setEvidenceView] = useState<unknown>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [clock, setClock] = useState(() => Math.floor(Date.now() / 1000));

  const remaining = useMemo(() => {
    if (!session?.session.expiresAtEpochSecond) return 0;
    return Math.max(0, session.session.expiresAtEpochSecond - clock);
  }, [clock, session]);

  const refresh = useCallback(async () => {
    if (!session) return;
    const next = await readJson<WorkbenchSession>(await fetch(
      `/api/live-workbench/sessions/${encodeURIComponent(session.session.sessionId)}`,
      { cache: "no-store" },
    ));
    setSession(next);
    setClock(next.serverNowEpochSecond);
  }, [session]);

  const refreshEvents = useCallback(async () => {
    if (!session) return;
    let after = events.at(-1)?.sequence ?? 0;
    for (let page = 0; page < 10; page += 1) {
      const id = encodeURIComponent(session.session.sessionId);
      const next = await readJson<RuntimeEvent[]>(await fetch(
        `/api/live-workbench/sessions/${id}/events?after=${after}&limit=500`,
        { cache: "no-store" },
      ));
      if (next.length === 0) break;
      setEvents((current) => {
        const sequences = new Set(current.map((item) => item.sequence));
        return [...current, ...next.filter((item) => !sequences.has(item.sequence))]
          .sort((left, right) => left.sequence - right.sequence)
          .slice(-500);
      });
      after = next.at(-1)?.sequence ?? after;
      if (next.length < 500) break;
    }
  }, [events, session]);

  useEffect(() => {
    if (!session || terminal.has(session.session.state)) return;
    const timer = window.setInterval(() => {
      setClock((value) => value + 1);
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [session]);

  useEffect(() => {
    if (!session || terminal.has(session.session.state)) return;
    const poll = window.setInterval(() => {
      void refresh().catch((failure) => setError(failure instanceof Error ? failure.message : "STATUS_FAILED"));
    }, 5_000);
    return () => window.clearInterval(poll);
  }, [refresh, session]);

  useEffect(() => {
    if (!session || terminal.has(session.session.state)) return;
    const poll = window.setInterval(() => {
      void refreshEvents().catch((failure) => setError(failure instanceof Error ? failure.message : "EVENT_REPLAY_FAILED"));
    }, 2_000);
    return () => window.clearInterval(poll);
  }, [refreshEvents, session]);

  useEffect(() => {
    if (!session || terminal.has(session.session.state) || remaining === 0) setPreviewUrl("");
  }, [remaining, session]);

  useEffect(() => {
    if (!session || terminal.has(session.session.state)) return;
    const id = encodeURIComponent(session.session.sessionId);
    const stream = new EventSource(`/api/live-workbench/sessions/${id}/events/stream?after=${events.at(-1)?.sequence ?? 0}`);
    const accept = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data) as RuntimeEvent;
        if (typeof parsed.sequence !== "number") return;
        setEvents((current) => current.some((item) => item.sequence === parsed.sequence)
          ? current
          : [...current, parsed].sort((left, right) => left.sequence - right.sequence).slice(-500));
      } catch { /* cursor and heartbeat frames are intentionally ignored */ }
    };
    for (const kind of ["stdout", "stderr", "stopped", "continued", "diagnostic", "test-result"]) stream.addEventListener(kind, accept);
    // Native EventSource reconnect retains the original cursor; duplicate replay is removed by sequence.
    return () => stream.close();
  }, [session?.session.sessionId, session?.session.state]);

  async function create() {
    setBusy(true); setError(""); setEvents([]); setPreviewUrl("");
    try {
      if (!digestPattern.test(snapshotId)) throw new Error("SNAPSHOT_SHA256_REQUIRED");
      const response = await fetch("/api/live-workbench/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ deliveryId, repositoryId, snapshotId, runtimeProfileId, scenario, mode, slotWeight: 1, debugRequired: mode !== "run" }),
      });
      const next = await readJson<WorkbenchSession>(response);
      setSession(next); setClock(next.serverNowEpochSecond);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "SESSION_CREATE_FAILED");
    } finally { setBusy(false); }
  }

  async function debug(command: string) {
    if (!session) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/live-workbench/sessions/${encodeURIComponent(session.session.sessionId)}/debug-commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ generation: session.session.generation, command: {
          command, argumentsDigest: await digest("{}"), stopEpoch: events.at(-1)?.stopEpoch ?? 0,
          controlLeaseId: `ui-${session.session.sessionId}`,
        } }),
      });
      await readJson(response); await refresh();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "DEBUG_COMMAND_FAILED"); }
    finally { setBusy(false); }
  }

  async function terminate() {
    if (!session) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/live-workbench/sessions/${encodeURIComponent(session.session.sessionId)}/terminate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expectedVersion: session.session.version, reason: "user-request" }),
      });
      setSession(await readJson<WorkbenchSession>(response));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "TERMINATION_FAILED"); }
    finally { setBusy(false); }
  }

  async function openPreview() {
    if (!session) return;
    setBusy(true); setError("");
    try {
      const access = await readJson<{ url: string; expiresAtEpochSecond: number }>(await fetch(
        `/api/live-workbench/sessions/${encodeURIComponent(session.session.sessionId)}/preview-access`,
        { cache: "no-store" },
      ));
      setPreviewUrl(access.url);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "PREVIEW_ACCESS_FAILED"); }
    finally { setBusy(false); }
  }

  async function inspect(kind: "delivery" | "source" | "explanation" | "mission" | "correspondence") {
    setBusy(true); setError("");
    try {
      const request = kind === "delivery"
        ? fetch(`/api/live-workbench/deliveries/${encodeURIComponent(deliveryId)}`, { cache: "no-store" })
        : kind === "source"
          ? fetch(`/api/live-workbench/anchors/${encodeURIComponent(anchorId)}/source`, { cache: "no-store" })
          : kind === "explanation"
            ? fetch("/api/live-workbench/explanations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ anchorId, audience: "engineer", mode: "line" }) })
            : kind === "mission"
              ? fetch(`/api/live-workbench/missions/${encodeURIComponent(missionId)}`, { cache: "no-store" })
              : fetch(`/api/live-workbench/correspondences/${encodeURIComponent(correspondenceId)}`, { cache: "no-store" });
      setEvidenceView(await readJson(await request));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "EVIDENCE_QUERY_FAILED"); }
    finally { setBusy(false); }
  }

  async function submitAssessment() {
    if (!session || events.length === 0) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/live-workbench/missions/${encodeURIComponent(missionId)}/attempts`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ sessionId: session.session.sessionId, generation: session.session.generation,
          answersDigest: await digest(answers), runtimeEventIds: events.map((event) => event.eventId) }),
      });
      setEvidenceView(await readJson(response));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "ASSESSMENT_FAILED"); }
    finally { setBusy(false); }
  }

  return (
    <main className={styles.page}>
      <header className={styles.hero}>
        <div><span className={styles.eyebrow}>LW.V1 · PRODUCTION CONTROL PLANE</span><h1>Live Workbench</h1></div>
        <p>在不可变提交上阅读、运行与调试。预览仅在验证完成后开始固定 10 分钟计时，浏览器无法续期。</p>
      </header>

      <section className={styles.grid} aria-label="Live Workbench session setup">
        <label>交付物 ID<input value={deliveryId} onChange={(event) => setDeliveryId(event.target.value)} required /></label>
        <label>仓库 ID<input value={repositoryId} onChange={(event) => setRepositoryId(event.target.value)} required /></label>
        <label className={styles.wide}>不可变快照 SHA-256<input value={snapshotId} onChange={(event) => setSnapshotId(event.target.value)} placeholder="sha256:…" required /></label>
        <label>运行时 Profile<input value={runtimeProfileId} onChange={(event) => setRuntimeProfileId(event.target.value)} required /></label>
        <label>验证场景<input value={scenario} onChange={(event) => setScenario(event.target.value)} required /></label>
        <label>模式<select value={mode} onChange={(event) => setMode(event.target.value)}><option value="run">运行</option><option value="debug">调试</option><option value="compare">对比</option><option value="learn">学习</option></select></label>
        <button className={styles.primary} disabled={busy || !deliveryId || !repositoryId || !snapshotId} onClick={() => void create()}>{busy ? "处理中…" : "创建隔离会话"}</button>
      </section>

      {error && <div className={styles.error} role="alert">请求被安全门禁阻断：{error}</div>}

      <section className={styles.evidenceTools} aria-label="Source, explanation and learning tools">
        <div><label>源码锚点 ID<input value={anchorId} onChange={(event) => setAnchorId(event.target.value)} /></label><button disabled={busy || !anchorId} onClick={() => void inspect("source")}>读取不可变选区</button><button disabled={busy || !anchorId} onClick={() => void inspect("explanation")}>证据解释</button></div>
        <div><label>课程 ID<input value={missionId} onChange={(event) => setMissionId(event.target.value)} /></label><button disabled={busy || !missionId} onClick={() => void inspect("mission")}>载入课程</button></div>
        <div><label>转换映射 ID<input value={correspondenceId} onChange={(event) => setCorrespondenceId(event.target.value)} /></label><button disabled={busy || !correspondenceId} onClick={() => void inspect("correspondence")}>查看来源映射</button></div>
        <button disabled={busy || !deliveryId} onClick={() => void inspect("delivery")}>检查交付能力</button>
        <label className={styles.answer}>练习答案（仅计算摘要，正文不会发送）<textarea value={answers} onChange={(event) => setAnswers(event.target.value)} /></label>
        <button disabled={busy || !missionId || !answers || session?.session.state !== "READY" || events.length === 0} onClick={() => void submitAssessment()}>提交服务端评估</button>
        {evidenceView !== null && <pre tabIndex={0}>{typeof evidenceView === "object" ? JSON.stringify(evidenceView, null, 2) : String(evidenceView)}</pre>}
      </section>

      {session && <section className={styles.runtime} aria-live="polite">
        <div className={styles.statusRow}>
          <div><span>状态</span><strong data-state={session.session.state}>{session.session.state}</strong></div>
          <div><span>剩余时间</span><strong className={styles.timer}>{formatRemaining(remaining)}</strong></div>
          <div><span>Generation</span><strong>{session.session.generation}</strong></div>
          <div><span>版本</span><strong>{session.session.version}</strong></div>
        </div>
        <p className={styles.identity}>{session.session.sessionId} · {session.session.snapshotId}</p>
        <div className={styles.controls} aria-label="Debugger controls">
          <button disabled={busy || session.session.state !== "READY" || remaining === 0} onClick={() => void openPreview()}>获取预览入口</button>
          {["pause", "continue", "next", "stepIn", "stepOut", "stackTrace", "variables"].map((command) =>
            <button key={command} disabled={busy || session.session.state !== "READY" || remaining === 0} onClick={() => void debug(command)}>{command}</button>)}
          <button className={styles.danger} disabled={busy || terminal.has(session.session.state)} onClick={() => void terminate()}>终止并回收</button>
        </div>
        {previewUrl && <p className={styles.preview}><a href={previewUrl} target="_blank" rel="noreferrer">在隔离环境中打开预览</a><small>临时入口不会晚于当前会话截止时间失效。</small></p>}
        <div className={styles.timeline}>
          <h2>可恢复运行事件</h2>
          {events.length === 0 ? <p>尚无已提交事件。断线后将按 sequence 游标重放。</p> : <ol>{events.map((event) =>
            <li key={`${event.sequence}-${event.eventId}`}><time>{new Date(event.serverTimeEpochSecond * 1000).toLocaleTimeString()}</time><strong>{event.kind}</strong><code>{event.payloadDigest}</code><small>{event.redactionStatus}</small></li>)}</ol>}
        </div>
      </section>}
    </main>
  );
}
