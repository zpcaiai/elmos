"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { StatusChip } from "../components/StatusChip";
import type {
  ModernizationProofContract,
  ModernizationProofJob,
  ModernizationProofSubmission,
} from "../lib/server/modernizationProofClient";

const terminal = new Set<ModernizationProofJob["status"]>([
  "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED", "LOST",
]);

type ErrorPayload = { reason?: string; code?: string };

async function responseJson<T>(response: Response, fallback: string): Promise<T> {
  let payload: unknown = {};
  try { payload = await response.json(); } catch { /* mapped below */ }
  if (!response.ok) {
    const error = payload as ErrorPayload;
    throw new Error(error.reason ?? error.code ?? fallback);
  }
  return payload as T;
}

function jsonObject(raw: string, field: string): Record<string, unknown> {
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${field}_MUST_BE_JSON_OBJECT`);
  }
  return parsed as Record<string, unknown>;
}

export function ModernizationProofStudio() {
  const [contracts, setContracts] = useState<ModernizationProofContract[]>([]);
  const [targetSkillId, setTargetSkillId] = useState("B108-S16");
  const [projectId, setProjectId] = useState("");
  const [repositoryId, setRepositoryId] = useState("");
  const [baselineCommit, setBaselineCommit] = useState("");
  const [candidateCommit, setCandidateCommit] = useState("");
  const [imageDigest, setImageDigest] = useState("");
  const [policyDigest, setPolicyDigest] = useState("");
  const [inputs, setInputs] = useState("{}");
  const [evidence, setEvidence] = useState("{}");
  const [subjectDigest, setSubjectDigest] = useState("");
  const [job, setJob] = useState<ModernizationProofJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(
    () => contracts.find((contract) => contract.id === targetSkillId),
    [contracts, targetSkillId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/modernization-proof/contracts", { cache: "no-store", signal: controller.signal })
      .then((response) => responseJson<ModernizationProofContract[]>(response, "CONTRACT_DISCOVERY_FAILED"))
      .then((rows) => setContracts(rows))
      .catch((reason: unknown) => {
        if (!(reason instanceof Error && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "CONTRACT_DISCOVERY_FAILED");
        }
      });
    return () => controller.abort();
  }, []);

  const refreshJob = useCallback(async (jobId: string, signal?: AbortSignal) => {
    const response = await fetch(`/api/modernization-proof/jobs/${encodeURIComponent(jobId)}`, {
      cache: "no-store", signal,
    });
    const value = await responseJson<ModernizationProofJob>(response, "PROOF_JOB_STATUS_FAILED");
    setJob(value);
    return value;
  }, []);

  useEffect(() => {
    if (!job || terminal.has(job.status)) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void refreshJob(job.jobId, controller.signal).catch((reason: unknown) => {
        if (!(reason instanceof Error && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "PROOF_JOB_STATUS_FAILED");
        }
      });
    }, 1_500);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [job, refreshJob]);

  function submission(): ModernizationProofSubmission {
    return {
      targetSkillId,
      projectId: projectId.trim(),
      repositoryId: repositoryId.trim(),
      ...(baselineCommit.trim() ? { baselineCommit: baselineCommit.trim() } : {}),
      ...(candidateCommit.trim() ? { candidateCommit: candidateCommit.trim() } : {}),
      ...(imageDigest.trim() ? { imageDigest: imageDigest.trim() } : {}),
      policyDigest: policyDigest.trim(),
      inputs: jsonObject(inputs, "INPUTS"),
      evidence: jsonObject(evidence, "EVIDENCE"),
    };
  }

  async function submit() {
    setBusy(true);
    setError("");
    setSubjectDigest("");
    try {
      const body = submission();
      const digestResponse = await fetch("/api/modernization-proof/subject-digest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          projectId: body.projectId,
          repositoryId: body.repositoryId,
          baselineCommit: body.baselineCommit,
          candidateCommit: body.candidateCommit,
          imageDigest: body.imageDigest,
          policyDigest: body.policyDigest,
        }),
      });
      const digest = await responseJson<{ subjectDigest: string }>(digestResponse, "SUBJECT_DIGEST_FAILED");
      setSubjectDigest(digest.subjectDigest);

      const createResponse = await fetch("/api/modernization-proof/jobs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const accepted = await responseJson<{ jobId: string }>(createResponse, "PROOF_JOB_CREATE_FAILED");
      await refreshJob(accepted.jobId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "PROOF_JOB_CREATE_FAILED");
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!job || terminal.has(job.status)) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/modernization-proof/jobs/${encodeURIComponent(job.jobId)}`, {
        method: "DELETE",
      });
      setJob(await responseJson<ModernizationProofJob>(response, "PROOF_JOB_CANCEL_FAILED"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "PROOF_JOB_CANCEL_FAILED");
    } finally {
      setBusy(false);
    }
  }

  return <div className="proof-loop-page">
    <section className="page-hero compact-hero">
      <div><span className="eyebrow">BATCH 105–108 · EVIDENCE-BOUND</span><h1>现代化生产证据闭环</h1></div>
      <p>从 Golden Route、隔离预览、实时 API/浏览器验证，到证据 PR 与客户证书。缺失或过期的独立证据保持 <code>BLOCKED</code>，本地执行不会授予生产批准。</p>
    </section>

    <div className="studio-layout proof-loop-layout">
      <section className="surface-card" aria-labelledby="proof-loop-form-title">
        <div className="card-heading"><div><span className="overline">DURABLE TENANT JOB</span><h2 id="proof-loop-form-title">提交验证计划</h2></div><StatusChip status={job?.resultStatus ?? "NOT_RUN"} compact /></div>
        <div className="business-form-grid">
          <label><span>闭环目标 Skill</span><select value={targetSkillId} onChange={(event) => setTargetSkillId(event.target.value)} required>
            {contracts.length ? contracts.map((contract) => <option key={contract.id} value={contract.id}>{contract.id} · {contract.name}</option>) : <option value="B108-S16">B108-S16 · customer-ready-modernization-certificate</option>}
          </select></label>
          <label><span>项目 ID</span><input value={projectId} onChange={(event) => setProjectId(event.target.value)} required pattern="[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}" autoComplete="off" /></label>
          <label><span>仓库 ID</span><input value={repositoryId} onChange={(event) => setRepositoryId(event.target.value)} required pattern="[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}" autoComplete="off" /></label>
          <label><span>策略摘要</span><input value={policyDigest} onChange={(event) => setPolicyDigest(event.target.value)} required pattern="(?:sha256:)?[a-f0-9]{64}" placeholder="sha256:…" spellCheck={false} /></label>
          <label><span>Baseline Commit（可选）</span><input value={baselineCommit} onChange={(event) => setBaselineCommit(event.target.value)} pattern="[a-f0-9]{40,64}" spellCheck={false} /></label>
          <label><span>Candidate Commit（可选）</span><input value={candidateCommit} onChange={(event) => setCandidateCommit(event.target.value)} pattern="[a-f0-9]{40,64}" spellCheck={false} /></label>
          <label className="proof-wide"><span>OCI 镜像摘要（可选）</span><input value={imageDigest} onChange={(event) => setImageDigest(event.target.value)} pattern="(?:sha256:)?[a-f0-9]{64}" placeholder="sha256:…" spellCheck={false} /></label>
          <label className="proof-wide"><span>类型化 Inputs JSON</span><textarea value={inputs} onChange={(event) => setInputs(event.target.value)} rows={8} spellCheck={false} /></label>
          <label className="proof-wide"><span>独立 Evidence Assertions JSON</span><textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} rows={10} spellCheck={false} /></label>
        </div>
        <p className="form-note">提交不会重试非幂等写操作；服务端按租户、Actor 与规范请求摘要生成幂等键。证据必须含独立 Producer/Verifier、签名校验、重算字节和内容地址。</p>
        <div className="business-actions">
          <button className="button button-primary" type="button" disabled={busy || !projectId.trim() || !repositoryId.trim() || !policyDigest.trim()} onClick={() => void submit()}>{busy ? "处理中…" : "提交证据闭环"}</button>
          {job && !terminal.has(job.status) ? <button className="button button-secondary" type="button" disabled={busy} onClick={() => void cancel()}>取消作业</button> : null}
        </div>
        {error ? <p className="field-error" role="alert">{error}</p> : null}
      </section>

      <aside className="surface-card detail-panel proof-loop-summary" aria-labelledby="proof-loop-summary-title">
        <div className="card-heading"><div><span className="overline">FAIL-CLOSED STATUS</span><h2 id="proof-loop-summary-title">计划与证据</h2></div></div>
        {selected ? <dl>
          <div><dt>目标</dt><dd><code>{selected.id}</code></dd></div>
          <div><dt>执行边界</dt><dd>{selected.executionClass}</dd></div>
          <div><dt>合同摘要</dt><dd><code>{selected.canonicalSha256.slice(0, 22)}…</code></dd></div>
          <div><dt>直接依赖</dt><dd>{selected.dependencies.join(", ") || "无"}</dd></div>
        </dl> : <p>正在读取 64 个不可变合同…</p>}
        {subjectDigest ? <div className="proof-subject"><span>Subject Digest</span><code>{subjectDigest}</code></div> : null}
        {selected ? <details><summary>声明的证据槽位</summary><ul>{selected.evidenceSlots.map((slot) => <li key={slot}><code>{slot}</code></li>)}</ul></details> : null}
        {job ? <div className="proof-job" aria-live="polite">
          <div className="generation-progress" aria-label={`作业进度 ${job.progress}%`}><i style={{ width: `${job.progress}%` }} /></div>
          <dl>
            <div><dt>Job</dt><dd><code>{job.jobId}</code></dd></div>
            <div><dt>队列状态</dt><dd>{job.status}</dd></div>
            <div><dt>证据结果</dt><dd>{job.resultStatus}</dd></div>
            <div><dt>阶段</dt><dd>{job.stage}</dd></div>
            {job.failureCode ? <div><dt>失败代码</dt><dd>{job.failureCode}</dd></div> : null}
          </dl>
          {job.artifacts?.length ? <ul className="proof-artifacts">{job.artifacts.map((artifact) => <li key={`${artifact.role}:${artifact.contentSha256}`}><strong>{artifact.role}</strong><span>{artifact.filename}</span><code>{artifact.contentSha256.slice(0, 22)}… · {artifact.byteSize} B</code></li>)}</ul> : <p className="form-note">结果工件尚未由对象存储发布。</p>}
        </div> : <p className="form-note">尚未提交。即使代码构建通过，外部 Provider、浏览器、SCM 与客户验收证据也不会自动变成 PASS。</p>}
      </aside>
    </div>
  </div>;
}
