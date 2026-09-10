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
      })();
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
      })();
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
