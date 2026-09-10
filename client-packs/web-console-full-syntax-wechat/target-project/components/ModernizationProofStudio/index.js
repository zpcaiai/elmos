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
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_0
      try {
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
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_1
      try {
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
      } catch (err) {
        console.error("Effect execution error:", err);
      }
    },
    detached() {
    },
  },
  methods: {
    submission() {
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
    },
    submit() {
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
    },
    cancel() {
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
    },
  },
});
