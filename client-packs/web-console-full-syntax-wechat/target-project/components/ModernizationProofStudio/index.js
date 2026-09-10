// Top-level helpers and constants
try { const terminal = new Set([
    "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED", "LOST",
]); } catch(e) {}
try { async function responseJson(response, fallback) {
    let payload = {};
    try {
        payload = await response.json();
    }
    catch { /* mapped below */ }
    if (!response.ok) {
        const error = payload;
        throw new Error(error.reason ?? error.code ?? fallback);
    }
    return payload;
} } catch(e) {}
try { function jsonObject(raw, field) {
    const parsed = JSON.parse(raw);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error(`${field}_MUST_BE_JSON_OBJECT`);
    }
    return parsed;
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    contracts: [],
    targetSkillId: "B108-S16",
    projectId: "",
    repositoryId: "",
    baselineCommit: "",
    candidateCommit: "",
    imageDigest: "",
    policyDigest: "",
    inputs: "{}",
    evidence: "{}",
    subjectDigest: "",
    job: null,
    busy: false,
    error: "",
    selected: null,
  },
  lifetimes: {
    attached() {
      const setContracts = (val) => { this.setData({ contracts: typeof val === "function" ? val(this.data.contracts) : val }); };
      const setTargetSkillId = (val) => { this.setData({ targetSkillId: typeof val === "function" ? val(this.data.targetSkillId) : val }); };
      const setProjectId = (val) => { this.setData({ projectId: typeof val === "function" ? val(this.data.projectId) : val }); };
      const setRepositoryId = (val) => { this.setData({ repositoryId: typeof val === "function" ? val(this.data.repositoryId) : val }); };
      const setBaselineCommit = (val) => { this.setData({ baselineCommit: typeof val === "function" ? val(this.data.baselineCommit) : val }); };
      const setCandidateCommit = (val) => { this.setData({ candidateCommit: typeof val === "function" ? val(this.data.candidateCommit) : val }); };
      const setImageDigest = (val) => { this.setData({ imageDigest: typeof val === "function" ? val(this.data.imageDigest) : val }); };
      const setPolicyDigest = (val) => { this.setData({ policyDigest: typeof val === "function" ? val(this.data.policyDigest) : val }); };
      const setInputs = (val) => { this.setData({ inputs: typeof val === "function" ? val(this.data.inputs) : val }); };
      const setEvidence = (val) => { this.setData({ evidence: typeof val === "function" ? val(this.data.evidence) : val }); };
      const setSubjectDigest = (val) => { this.setData({ subjectDigest: typeof val === "function" ? val(this.data.subjectDigest) : val }); };
      const setJob = (val) => { this.setData({ job: typeof val === "function" ? val(this.data.job) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
      const setError = (val) => { this.setData({ error: typeof val === "function" ? val(this.data.error) : val }); };
      // Lifecycle effect effect_0
      (async () => {
        try {
          const controller = new AbortController();
    void fetch("/api/modernization-proof/contracts", { cache: "no-store", signal: controller.signal })
        .then((response) => responseJson(response, "CONTRACT_DISCOVERY_FAILED"))
        .then((rows) => setContracts(rows))
        .catch((reason) => {
        if (!(reason instanceof Error && reason.name === "AbortError")) {
            setError(reason instanceof Error ? reason.message : "CONTRACT_DISCOVERY_FAILED");
        }
    });
    return () => controller.abort();
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_1
      (async () => {
        try {
          if (!job || terminal.has(job.status))
        return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
        void refreshJob(job.jobId, controller.signal).catch((reason) => {
            if (!(reason instanceof Error && reason.name === "AbortError")) {
                setError(reason instanceof Error ? reason.message : "PROOF_JOB_STATUS_FAILED");
            }
        });
    }, 1_500);
    return () => {
        controller.abort();
        window.clearTimeout(timer);
    };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    submission() {
      try {
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
      } catch (err) {
        console.warn("submission execution warning:", err);
      }
    },
    async submit() {
      try {
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
        const digest = await responseJson(digestResponse, "SUBJECT_DIGEST_FAILED");
        setSubjectDigest(digest.subjectDigest);
        const createResponse = await fetch("/api/modernization-proof/jobs", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(body),
        });
        const accepted = await responseJson(createResponse, "PROOF_JOB_CREATE_FAILED");
        await refreshJob(accepted.jobId);
    }
    catch (reason) {
        setError(reason instanceof Error ? reason.message : "PROOF_JOB_CREATE_FAILED");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("submit execution warning:", err);
      }
    },
    async cancel() {
      try {
        if (!job || terminal.has(job.status))
        return;
    setBusy(true);
    setError("");
    try {
        const response = await fetch(`/api/modernization-proof/jobs/${encodeURIComponent(job.jobId)}`, {
            method: "DELETE",
        });
        setJob(await responseJson(response, "PROOF_JOB_CANCEL_FAILED"));
    }
    catch (reason) {
        setError(reason instanceof Error ? reason.message : "PROOF_JOB_CANCEL_FAILED");
    }
    finally {
        setBusy(false);
    }
      } catch (err) {
        console.warn("cancel execution warning:", err);
      }
    },
  },
});
