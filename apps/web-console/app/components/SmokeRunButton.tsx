"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { StatusChip } from "./StatusChip";
import styles from "./SmokeRunButton.module.css";
import type {
  SmokeCapabilityResponse,
  SmokeEntry,
  SmokeEvidenceBundle,
  SmokePackSummary,
  SmokeSession,
} from "../lib/smokeContracts";

/**
 * 「一键运行」按钮。
 *
 * 生成或转换完成后放在结果区，接收方点一下就能把产物跑起来，10 分钟免费额度
 * 到期后由 Batch 46 租约看门狗回收；本组件只负责显示真实状态，不自行判断
 * 是否通过，也不隐藏任何 NOT_RUN。
 */

const LIVE_STATES = new Set(["STARTING", "RUNNING", "READY", "HOLDING"]);
const ENTRY_LABELS: Record<SmokeEntry, string> = {
  script: "脚本入口（最接近真实运行方式）",
  compose: "容器编排（最接近真实拓扑，需 Docker）",
  make: "Make 目标（CI 友好）",
  "zero-dep": "零依赖（最快跑通，非声明引擎）",
};
const LOCATION_LABELS: Record<string, string> = {
  HOSTED_RUNNER: "服务端沙箱",
  LOCAL_WORKSTATION: "接收方本机",
};
const EXTENSION_CHOICES = [
  { seconds: 300, label: "5 分钟" },
  { seconds: 600, label: "10 分钟" },
  { seconds: 1_800, label: "30 分钟" },
];

function clock(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T & { status?: string; reason?: string };
  if (!response.ok || payload.status === "BLOCKED") {
    throw new Error(payload.reason ?? `HTTP_${response.status}`);
  }
  return payload;
}

export function SmokeRunButton({ projectRef }: { projectRef: string }) {
  const [capability, setCapability] = useState<SmokeCapabilityResponse | null>(null);
  const [pack, setPack] = useState<SmokePackSummary | null>(null);
  const [session, setSession] = useState<SmokeSession | null>(null);
  const [evidence, setEvidence] = useState<SmokeEvidenceBundle | null>(null);
  const [entry, setEntry] = useState<SmokeEntry | "">("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState(0);
  const [extendOpen, setExtendOpen] = useState(false);
  const [extendSeconds, setExtendSeconds] = useState(300);
  const [extendReason, setExtendReason] = useState("");
  const [extendActor, setExtendActor] = useState("");
  const expiresAtRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [capabilityResponse, packResponse] = await Promise.all([
          fetch("/api/smoke/capability", { cache: "no-store" }),
          fetch(`/api/smoke/pack?projectRef=${encodeURIComponent(projectRef)}`, { cache: "no-store" }),
        ]);
        const nextCapability = await readJson<SmokeCapabilityResponse>(capabilityResponse);
        const nextPack = await readJson<SmokePackSummary>(packResponse);
        if (cancelled) return;
        setCapability(nextCapability);
        setPack(nextPack);
        setEntry(nextPack.defaultEntry ?? nextPack.entries.find((item) => item.status === "available")?.entry ?? "");
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "SMOKE_LOAD_FAILED");
      }
    })();
    return () => { cancelled = true; };
  }, [projectRef]);

  const applySession = useCallback((next: SmokeSession) => {
    setSession(next);
    // The countdown is rendered locally but the deadline is always the server's.
    expiresAtRef.current = next.expiresAtEpoch;
    setRemaining(next.remainingSeconds);
  }, []);

  const live = session !== null && LIVE_STATES.has(session.state) && remaining > 0;

  // Poll the session while it is live; the run outlives this page, so state comes
  // from the pack's own evidence rather than from anything held in the browser.
  useEffect(() => {
    if (!session || !LIVE_STATES.has(session.state)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await readJson<SmokeSession>(
          await fetch(`/api/smoke/sessions/${session.sessionId}`, { cache: "no-store" }),
        );
        applySession(next);
      } catch {
        /* transient poll failure: the local countdown keeps running */
      }
    }, 3_000);
    return () => window.clearInterval(timer);
  }, [session, applySession]);

  useEffect(() => {
    if (!session || !LIVE_STATES.has(session.state)) return;
    const timer = window.setInterval(() => {
      const expiresAt = expiresAtRef.current;
      setRemaining(expiresAt ? Math.max(0, Math.round(expiresAt * 1_000 - Date.now()) / 1_000) : 0);
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [session]);

  const call = useCallback(async (action: () => Promise<SmokeSession>) => {
    setBusy(true);
    setError(null);
    try {
      applySession(await action());
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "SMOKE_ACTION_FAILED");
    } finally {
      setBusy(false);
    }
  }, [applySession]);

  const start = useCallback(() => {
    setEvidence(null);
    return call(async () => readJson<SmokeSession>(await fetch("/api/smoke/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ projectRef, entry: entry || undefined }),
    })));
  }, [call, projectRef, entry]);

  const stop = useCallback(() => {
    if (!session) return;
    void call(async () => readJson<SmokeSession>(
      await fetch(`/api/smoke/sessions/${session.sessionId}/stop`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reason: "manual" }),
      }),
    ));
  }, [call, session]);

  const extend = useCallback(() => {
    if (!session) return;
    void call(async () => {
      const next = await readJson<SmokeSession>(
        await fetch(`/api/smoke/sessions/${session.sessionId}/extend`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            seconds: extendSeconds,
            reason: extendReason.trim(),
            actor: extendActor.trim() || undefined,
          }),
        }),
      );
      setExtendOpen(false);
      setExtendReason("");
      return next;
    });
  }, [call, session, extendSeconds, extendReason, extendActor]);

  const loadEvidence = useCallback(async () => {
    if (!session) return;
    setBusy(true);
    try {
      setEvidence(await readJson<SmokeEvidenceBundle>(
        await fetch(`/api/smoke/sessions/${session.sessionId}/evidence`, { cache: "no-store" }),
      ));
    } catch (evidenceError) {
      setError(evidenceError instanceof Error ? evidenceError.message : "SMOKE_EVIDENCE_FAILED");
    } finally {
      setBusy(false);
    }
  }, [session]);

  const selectedEntry = useMemo(
    () => pack?.entries.find((item) => item.entry === entry) ?? null,
    [pack, entry],
  );
  const runnableLocation = capability?.preferredLocation ?? null;
  const blockedLocations = (capability?.locations ?? []).filter((item) => item.status !== "AVAILABLE");
  const canStart = Boolean(
    pack && runnableLocation && selectedEntry?.status === "available" && !busy && !live,
  );
  const expired = session !== null && !live && session.state !== "STARTING";
  const extensionValid = extendReason.trim().length >= 4;

  return (
    <section className={styles.panel} aria-label="一键冒烟运行">
      <div className={styles.header}>
        <div>
          <h3>一键运行冒烟测试</h3>
          <p className={styles.subtitle}>
            用生成的一次性数据把产物跑起来，验证「能启动、能响应一次请求、能干净退出」。
            免费额度 {Math.round((capability?.freeQuotaSeconds ?? 600) / 60)} 分钟，到期自动停止服务、删除容器与卷、清空临时数据。
            冒烟结果不构成路线等价、性能、安全或认证证据。
          </p>
        </div>
        {session ? <StatusChip status={session.state} /> : <StatusChip status="NOT_RUN" />}
      </div>

      {pack ? (
        <div className={styles.facts}>
          {pack.languages.map((language) => <span key={language} className={styles.fact}>{language}</span>)}
          {pack.frameworks.map((framework) => <span key={framework} className={styles.fact}>{framework}</span>)}
          {pack.datastores.map((store) => <span key={store} className={styles.fact}>{store}</span>)}
          {runnableLocation ? (
            <span className={styles.fact}>执行位置：{LOCATION_LABELS[runnableLocation] ?? runnableLocation}</span>
          ) : null}
        </div>
      ) : null}

      {pack && pack.unknownCount > 0 ? (
        <p className={`${styles.notice} ${styles.noticeWarning}`}>
          该冒烟包仍有 {pack.unknownCount} 项未解决的未知项，运行可以进行，但门禁会因此阻断认证。
        </p>
      ) : null}

      <div className={styles.controls}>
        <label className={styles.entrySelect}>
          <span>运行入口</span>
          <select
            value={entry}
            onChange={(event) => setEntry(event.target.value as SmokeEntry)}
            disabled={live || busy || !pack}
          >
            {(pack?.entries ?? []).map((item) => (
              <option key={item.entry} value={item.entry} disabled={item.status !== "available"}>
                {ENTRY_LABELS[item.entry]}{item.status === "available" ? "" : "（不可用）"}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          className={`button button-primary ${styles.runButton}`}
          onClick={() => void start()}
          disabled={!canStart}
        >
          {busy && !session ? "正在启动…"
            : live ? "运行中"
            : expired ? "重新运行（新的免费额度）"
            : `一键运行（免费 ${Math.round((capability?.freeQuotaSeconds ?? 600) / 60)} 分钟）`}
        </button>

        {live ? (
          <button type="button" className="button button-secondary" onClick={stop} disabled={busy}>
            立即停止并回收
          </button>
        ) : null}
        {live ? (
          <button
            type="button"
            className="button button-secondary"
            onClick={() => setExtendOpen((open) => !open)}
            disabled={busy}
          >
            续期
          </button>
        ) : null}
      </div>

      {selectedEntry?.status === "unavailable" && selectedEntry.reason ? (
        <p className={`${styles.notice} ${styles.noticeBlocked}`}>入口不可用：{selectedEntry.reason}</p>
      ) : null}
      {selectedEntry?.semanticWarning ? (
        <p className={`${styles.notice} ${styles.noticeWarning}`}>{selectedEntry.semanticWarning}</p>
      ) : null}
      {!runnableLocation && capability ? (
        <p className={`${styles.notice} ${styles.noticeBlocked}`}>
          当前没有可用的执行位置，无法运行：
          {blockedLocations.map((item) => `${LOCATION_LABELS[item.location] ?? item.location} — ${item.reason ?? item.status}`).join("；")}
        </p>
      ) : null}
      {error ? <p className={`${styles.notice} ${styles.noticeBlocked}`}>操作失败：{error}</p> : null}

      {live && session ? (
        <div className={`${styles.countdown} ${remaining <= 60 ? styles.countdownExpiring : ""}`}>
          <span className={styles.countdownClock}>{clock(remaining)}</span>
          <span className={styles.countdownLabel}>
            剩余免费运行时间
            {session.billableSeconds > 0 ? `（其中 ${session.billableSeconds} 秒超出免费额度，计入计费）` : ""}
            <br />
            {session.url ? (
              <a className={styles.serviceLink} href={session.url} target="_blank" rel="noreferrer">
                {session.url}
              </a>
            ) : "服务地址分配中…"}
          </span>
        </div>
      ) : null}

      {extendOpen && live ? (
        <div className={styles.extendForm}>
          <p className={styles.subtitle}>
            续期不会自动发生，必须写明理由与操作人。超出免费额度的秒数会被记录为计费时长。
          </p>
          <div className={styles.extendGrid}>
            <label>
              <span>时长</span>
              <select value={extendSeconds} onChange={(event) => setExtendSeconds(Number(event.target.value))}>
                {EXTENSION_CHOICES.map((choice) => (
                  <option key={choice.seconds} value={choice.seconds}>{choice.label}</option>
                ))}
              </select>
            </label>
            <label>
              <span>理由（必填，至少 4 个字符）</span>
              <input
                value={extendReason}
                onChange={(event) => setExtendReason(event.target.value)}
                placeholder="例如：复现 POST /orders 的 500"
                maxLength={240}
              />
            </label>
            <label>
              <span>操作人</span>
              <input
                value={extendActor}
                onChange={(event) => setExtendActor(event.target.value)}
                placeholder="留空则使用当前账号"
                maxLength={120}
              />
            </label>
          </div>
          <div className={styles.controls}>
            <button
              type="button"
              className="button button-primary"
              onClick={extend}
              disabled={!extensionValid || busy}
            >
              确认续期 {EXTENSION_CHOICES.find((choice) => choice.seconds === extendSeconds)?.label}
            </button>
            <button type="button" className="button button-secondary" onClick={() => setExtendOpen(false)}>
              取消
            </button>
          </div>
        </div>
      ) : null}

      {session && session.checks.length > 0 ? (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>冒烟断言</span>
          <ul className={styles.checks}>
            {session.checks.map((check) => (
              <li key={check.id} className={styles.checkRow}>
                <StatusChip status={check.status} compact />
                <span className={styles.checkId}>{check.id}{check.required ? "" : "（非必需）"}</span>
                <span className={styles.checkDetail}>{check.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {session?.notes.length ? (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>运行说明</span>
          {session.notes.map((note) => <p key={note} className={styles.notice}>{note}</p>)}
        </div>
      ) : null}

      {session?.extensions.length ? (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>续期记录</span>
          <ul className={styles.teardownList}>
            {session.extensions.map((item, index) => (
              <li key={`${item.grantedAt}-${index}`}>
                {item.grantedAt} · {item.seconds} 秒 · {item.actor} · {item.reason}
                {item.beyondFreeQuota ? "（超出免费额度）" : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {expired && session?.teardown ? (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>
            回收报告（{session.teardown.reason === "expired" ? "额度到期" : "手工停止"}）
          </span>
          <ul className={styles.teardownList}>
            <li>
              进程：{session.teardown.processes.length} 个
              {session.teardown.processes.some((item) => item.killed)
                ? "，其中有进程未在宽限期内响应 SIGTERM，已强制终止"
                : "，全部在宽限期内优雅退出"}
            </li>
            <li>
              容器编排：{session.teardown.compose.length === 0
                ? "本次运行未启动容器"
                : session.teardown.compose.map((item) => `${item.status}`).join("、")}
            </li>
            <li>
              临时数据：已删除 {session.teardown.removedPaths.filter((item) => item.removed !== "absent").length} 项
              {session.teardown.removedPaths.some((item) => item.removed === "failed") ? "，存在删除失败项" : ""}
            </li>
            <li>回收结论：{session.teardown.complete ? "无残留" : "存在残留，门禁将阻断"}</li>
          </ul>
        </div>
      ) : null}

      {expired && session ? (
        <div className={styles.section}>
          <span className={styles.sectionTitle}>门禁结论</span>
          <p className={styles.notice}>
            <StatusChip status={session.gateStatus.toUpperCase()} compact /> · 服务已回收，证据与日志仍然保留。
          </p>
          {session.gateFailures.map((failure) => (
            <p key={failure} className={`${styles.notice} ${styles.noticeBlocked}`}>阻断：{failure}</p>
          ))}
          {session.gateLimitations.map((limitation) => (
            <p key={limitation} className={`${styles.notice} ${styles.noticeWarning}`}>受限：{limitation}</p>
          ))}
          <div className={styles.controls}>
            <button type="button" className="button button-secondary" onClick={() => void loadEvidence()} disabled={busy}>
              查看证据与日志
            </button>
          </div>
        </div>
      ) : null}

      {evidence ? (
        <div className={styles.evidence}>
          <span className={styles.sectionTitle}>证据（到期后保留）</span>
          {evidence.logs.map((log) => (
            <details key={log.name}>
              <summary className={styles.checkId}>{log.name}（{log.bytes} 字节，显示尾部）</summary>
              <pre className={styles.logBlock}>{log.tail || "（空）"}</pre>
            </details>
          ))}
          <details>
            <summary className={styles.checkId}>result.json</summary>
            <pre className={styles.logBlock}>{JSON.stringify(evidence.result, null, 2)}</pre>
          </details>
          <details>
            <summary className={styles.checkId}>lease-result.json</summary>
            <pre className={styles.logBlock}>{JSON.stringify(evidence.lease, null, 2)}</pre>
          </details>
        </div>
      ) : null}
    </section>
  );
}
