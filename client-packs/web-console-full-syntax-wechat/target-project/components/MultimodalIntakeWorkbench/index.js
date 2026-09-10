Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    projectId: "default-project",
    directText: "",
    assets: [],
    recoveryRecordCount: 0,
    legacyRecoveryCount: 0,
    recoveryStoreReady: false,
    recoveryStoreError: "",
    busy: false,
    reviewBusy: false,
    feedback: "",
    treeQuery: "",
    packagePreview: null,
    packagePage: null,
    packagePageCursors: [null],
    packagePageIndex: 0,
    estimate: null,
    estimateBusy: false,
    correction: "",
    correctionTouched: false,
    correctionTarget: "",
    reviewTasks: [],
    reviewSources: [],
    selectedReviewSourceKey: "",
    selectedReviewTaskId: "",
    reviewTargetKind: "TEXT",
    reviewTargetLocator: "",
    reviewOriginalValue: "",
    reviewConfidence: "0.5",
    reviewReason: "USER_REVIEW",
    reviewPropagation: null,
    reviewCurrentCorrection: null,
    fileInput: null,
    folderInput: null,
    fileAdditionLock: false,
    fileAdditionOwner: 0,
    selectionCapacity: "{ count: 0, bytes: 0 }",
    recoveryByScope: "new Map<string, UploadRecoveryRecord>()",
    recoveryLoad: null,
    reviewClaims: {},
    reviewIdentityScope: "",
    legacyReviewClaimDiscarded: false,
    reviewEnqueueRecoveryCount: 0,
    reviewEnqueueRecoveryError: "",
    reviewClock: 0,
    reviewScopeGeneration: 0,
    reviewRequestOwner: 0,
    reviewEngineScope: null,
    recoveryIdentityGeneration: 0,
    activeIdentityScope: "",
    intakeBusyOwner: 0,
    estimateRequestOwner: 0,
    intakeProjectGeneration: 0,
    activeProjectId: "projectId",
  },
  lifetimes: {
    attached() {
      // Lifecycle effect effect_8
      try {
        let active = true;
    setReviewIdentityScope("");
    setReviewClaims({});
    if (account.status === "loading") return () => { active = false; };
    if (account.status === "anonymous") {
      try {
        const scopedKeys: string[] = [];
        for (let index = 0; index < sessionStorage.length; index += 1) {
          const key = sessionStorage.key(index);
          if (key && (
            key === legacyReviewClaimStorageKey
            || key.startsWith(`${reviewClaimStoragePrefix}:`)
            || key.startsWith(`${legacyReviewEnqueueStoragePrefix}:`)
          )) scopedKeys.push(key);
        }
        for (const key of scopedKeys) sessionStorage.removeItem(key);
      } catch {
        // Server-side actor binding remains authoritative when local cleanup fails.
      }
      // V2 enqueue recovery records contain only opaque handles, scoped
      // digests, and idempotency keys. Preserve those records so the same actor
      // can reconcile an UNKNOWN result after signing in again. Legacy V1
      // records contained the exact correction input and are removed above.
      return () => { active = false; };
    }
    const identity = account.status === "authenticated" && account.principal
      ? {
          schema_version: "multimodal-review-browser-scope-v1",
          organization_id: account.principal.organizationId,
          actor_id: account.principal.actorId,
        }
      : {
          schema_version: "multimodal-review-browser-scope-v1",
          local_runner: true,
        };
    void sha256(new TextEncoder().encode(canonicalStrictJson(identity)).buffer).then((digest) => {
      if (active) setReviewIdentityScope(`sha256:${digest}`);
    });
    return () => { active = false; };
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_12
      try {
        if (!reviewIdentityScope) return;
    try {
      const legacy = sessionStorage.getItem(legacyReviewClaimStorageKey);
      setLegacyReviewClaimDiscarded(legacy !== null);
      if (legacy !== null) sessionStorage.removeItem(legacyReviewClaimStorageKey);
      const rawEnqueueKeys: string[] = [];
      for (let index = 0; index < sessionStorage.length; index += 1) {
        const key = sessionStorage.key(index);
        if (key?.startsWith(`${legacyReviewEnqueueStoragePrefix}:`)) {
          rawEnqueueKeys.push(key);
        }
      }
      for (const key of rawEnqueueKeys) sessionStorage.removeItem(key);
    } catch {
      setLegacyReviewClaimDiscarded(false);
    }
    setReviewClaims(loadReviewClaims(reviewIdentityScope));
    void updateReviewEnqueueRecoveryState(reviewIdentityScope, projectId);
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_13
      try {
        const now = Date.now();
    const boundaries = [
      ...Object.values(reviewClaims).map((claim) => (
        claim.fence === undefined
          ? claim.created_at + pendingReviewClaimRecoveryMs
          : Date.parse(claim.expires_at as string)
      )),
      ...reviewTasks.flatMap((task) => (
        task.claim_expires_at ? [Date.parse(task.claim_expires_at)] : []
      )),
    ].filter((value) => Number.isFinite(value) && value > now);
    if (boundaries.length === 0) return undefined;
    const delay = Math.min(Math.min(...boundaries) - now + 25, 2_147_000_000);
    const timer = window.setTimeout(() => {
      setReviewClock((current) => current + 1);
      if (!reviewIdentityScope) return;
      const retained = Object.fromEntries(Object.entries(reviewClaims).filter(([, claim]) => (
        validReviewClaim(claim, reviewIdentityScope)
      ))) as Record<string, ReviewClaim>;
      if (
        Object.keys(retained).length !== Object.keys(reviewClaims).length
        && persistReviewClaims(retained, reviewIdentityScope)
      ) {
        setReviewClaims(retained);
      }
    }, delay);
    return () => window.clearTimeout(timer);
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_26
      try {
        if (reviewIdentityScope) void ensureRecoveryStore();
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_27
      try {
        if (typeof EventSource === "undefined" || !safeProject(projectId)) return undefined;
    const jobIds = parseStrictJson(activeProgressJobKey, {
      maximumDepth: 2,
      maximumNodes: maximumBatchAssets + 1,
    });
    if (!Array.isArray(jobIds) || jobIds.length === 0) return undefined;
    let active = true;
    const streams: EventSource[] = [];
    for (const value of jobIds) {
      if (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)) {
        continue;
      }
      const jobId = value;
      const stream = new EventSource(
        `/api/multimodal-intake/v1/progress/jobs/${encodeURIComponent(jobId)}`
        + `?projectId=${encodeURIComponent(projectId)}`,
        { withCredentials: true },
      );
      let streamClosed = false;
      const closeStream = () => {
        if (streamClosed) return;
        streamClosed = true;
        stream.close();
      };
      streams.push(stream);
      stream.addEventListener("progress", (rawEvent) => {
        const event = rawEvent as MessageEvent<string>;
        void validatedJobProgressEvent(event.data, jobId, event.lastEventId).then((progress) => {
          if (!active) return;
          const state = progress.state as string;
          const phase: AssetPhase = state === "COMPLETED"
            ? "READY"
            : ["PARTIAL", "NEEDS_REVIEW"].includes(state)
              ? "NEEDS_REVIEW"
              : ["FAILED", "BLOCKED", "CANCELLED"].includes(state)
                ? "BLOCKED"
                : "PROCESSING";
          const terminal = ["READY", "NEEDS_REVIEW", "BLOCKED"].includes(phase);
          setAssets((current) => current.map((asset) => (
            asset.processingJobId === jobId
              ? {
                  ...asset,
                  phase,
                  progress: terminal ? 100 : Math.max(asset.progress, 80),
                  ...(terminal ? { processingJobId: undefined } : {}),
                }
              : asset
          )));
          if (terminal) closeStream();
        }).catch(() => {
          closeStream();
          if (!active) return;
          setAssets((current) => current.map((asset) => (
            asset.processingJobId === jobId
              ? { ...asset, code: "MULTIMODAL_PROGRESS_EVENT_INVALID" }
              : asset
          )));
        });
      });
      stream.addEventListener("error", () => {
        // The BFF response is deliberately one bounded batch. Never let native
        // EventSource turn a close or transport failure into an unbounded retry
        // loop; the existing tenant-bound get_session poll is the sole fallback.
        closeStream();
        if (!active) return;
        setAssets((current) => current.map((asset) => (
          asset.processingJobId === jobId
            ? { ...asset, code: "MULTIMODAL_PROGRESS_STREAM_UNAVAILABLE_POLLING" }
            : asset
        )));
      });
    }
    return () => {
      active = false;
      for (const stream of streams) stream.close();
    };
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_31
      try {
        let identityGuard: IntakeIdentityGuard;
    try {
      identityGuard = captureIntakeIdentity();
    } catch {
      return undefined;
    }
    const sessions = [...new Set(
      assets
        .filter((asset) => asset.sessionId && !["READY", "QUARANTINED"].includes(asset.phase) && !asset.permanentBlock)
        .map((asset) => asset.sessionId as string),
    )];
    if (busy || !safeProject(projectId) || sessions.length === 0) return undefined;
    let active = true;
    const poll = async () => {
      for (const sessionId of sessions) {
        try {
          const response = await executeGuardedIntakeSkill(
            identityGuard,
            projectId,
            "elmos-multimodal-input-orchestrator",
            "get_session",
            { session_id: sessionId },
            `mmi-progress-${sessionId}-${Math.floor(Date.now() / 5_000)}`,
          );
          const observed = nestedRecord(response).assets;
          if (!active || !intakeIdentityIsCurrent(identityGuard) || !Array.isArray(observed)) continue;
          const byId = new Map(observed
            .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item) && typeof (item as Record<string, unknown>).asset_id === "string")
            .map((item) => [String(item.asset_id), {
              status: String(item.status ?? "PROCESSING").toUpperCase(),
              version: positiveInteger(item.version),
            }]));
          setAssets((current) => {
            let changed = false;
            const next = current.map((asset) => {
              const observedAsset = asset.assetId ? byId.get(asset.assetId) : undefined;
              if (!observedAsset) return asset;
              // Corrections create a new immutable asset version. A lagging
              // session snapshot must never regress that newer local state.
              if (
                asset.assetVersion
                && (!observedAsset.version || observedAsset.version < asset.assetVersion)
              ) return asset;
              const state = observedAsset.status;
              const phase: AssetPhase = state === "READY" || state === "COMPLETED"
                ? "READY"
                : state === "NEEDS_REVIEW" || state === "PARTIAL"
                  ? "NEEDS_REVIEW"
                  : state === "QUARANTINED"
                    ? "QUARANTINED"
                    : state === "FAILED" || state === "BLOCKED"
                      ? "BLOCKED"
                      : "PROCESSING";
              const progress = ["READY", "NEEDS_REVIEW", "QUARANTINED", "BLOCKED"].includes(phase)
                ? 100
                : Math.max(asset.progress, 80);
              if (
                phase === asset.phase
                && progress === asset.progress
                && (!observedAsset.version || observedAsset.version === asset.assetVersion)
              ) return asset;
              changed = true;
              return {
                ...asset,
                phase,
                progress,
                ...(observedAsset.version ? { assetVersion: observedAsset.version } : {}),
              };
            });
            return changed ? next : current;
          });
        } catch {
          // Recovery metadata remains authoritative for the next bounded poll.
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 5_000);
    return () => { active = false; window.clearInterval(timer); };
      } catch (err) {
        console.error("Effect execution error:", err);
      }
      // Lifecycle effect effect_45
      try {
        estimateRequestOwner.current += 1;
    setEstimate(null);
    setEstimateBusy(false);
      } catch (err) {
        console.error("Effect execution error:", err);
      }
    },
    detached() {
    },
  },
  methods: {
    captureIntakeIdentity() {
      const identityScope = activeIdentityScope.current;
    if (!identityScope)
        throw new Error("MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
    return {
        generation: recoveryIdentityGeneration.current,
        identityScope,
        projectGeneration: intakeProjectGeneration.current,
        projectId: activeProjectId.current,
    };
    },
    intakeIdentityIsCurrent(guard) {
      return guard.generation === recoveryIdentityGeneration.current
        && guard.identityScope === activeIdentityScope.current
        && guard.projectGeneration === intakeProjectGeneration.current
        && guard.projectId === activeProjectId.current;
    },
    assertIntakeIdentityCurrent(guard) {
      if (!intakeIdentityIsCurrent(guard))
    throw new Error("MULTIMODAL_IDENTITY_SCOPE_CHANGED");
    },
    executeGuardedIntakeSkill(guard, projectAlias, skill, operation, input, idempotencyKey) {
      assertIntakeIdentityCurrent(guard);
    if (projectAlias !== guard.projectId)
        throw new Error("MULTIMODAL_PROJECT_SCOPE_CHANGED");
    const response = await executeSkill(projectAlias, skill, operation, input, idempotencyKey);
    assertIntakeIdentityCurrent(guard);
    return response;
    },
    publishRecoveryRecords() {
      setRecoveryRecordCount(recoveryByScope.current.size);
    },
    recoveryRecords(projectAlias, fileFingerprint, engineProjectId) {
      return [...recoveryByScope.current.values()].filter((record) => record.projectId === projectAlias
        && record.fileFingerprint === fileFingerprint
        && (engineProjectId === undefined || record.engineProjectId === engineProjectId));
    },
    persistRecovery(record, guard) {
      assertIntakeIdentityCurrent(guard);
    if (!validRecoveryRecord(record)
        || record.identityScope !== guard.identityScope)
        throw new Error("RECOVERY_METADATA_INVALID");
    await putRecoveryValue(record);
    assertIntakeIdentityCurrent(guard);
    recoveryByScope.current.set(recoveryStorageKey(record), record);
    publishRecoveryRecords();
    },
    clearRecovery(record, guard) {
      assertIntakeIdentityCurrent(guard);
    if (!record.projectId || !record.engineProjectId) {
        throw new Error("RECOVERY_SCOPE_BINDING_MISSING");
    }
    const identity = {
        identityScope: guard.identityScope,
        projectId: record.projectId,
        engineProjectId: record.engineProjectId,
        fileFingerprint: record.fileFingerprint,
    };
    await deleteRecoveryValue(identity);
    assertIntakeIdentityCurrent(guard);
    recoveryByScope.current.delete(recoveryStorageKey(identity));
    publishRecoveryRecords();
    },
    recoveryFromAsset(asset, guard) {
      assertIntakeIdentityCurrent(guard);
    if (!asset.projectId
        || !asset.engineProjectId
        || !asset.sessionAttemptKey) {
        throw new Error("RECOVERY_SCOPE_OR_SESSION_BINDING_MISSING");
    }
    return {
        schemaVersion: 2,
        identityScope: guard.identityScope,
        fileFingerprint: asset.fileFingerprint,
        expectedSize: asset.file.size,
        lastModified: asset.file.lastModified,
        partSize: chunkBytes,
        attemptKey: asset.attemptKey,
        projectId: asset.projectId,
        engineProjectId: asset.engineProjectId,
        sessionAttemptKey: asset.sessionAttemptKey,
        ...(asset.sha256 ? { contentSha256: asset.sha256 } : {}),
        ...(asset.sessionId ? { sessionId: asset.sessionId } : {}),
        ...(asset.uploadSessionId ? { uploadSessionId: asset.uploadSessionId } : {}),
        confirmedPartCount: asset.confirmedPartCount,
        processingAttempt: asset.processingAttempt,
        ...(asset.assetId ? { assetId: asset.assetId } : {}),
        ...(asset.assetVersion ? { assetVersion: asset.assetVersion } : {}),
        role: asset.role,
        modelReadAllowed: asset.modelReadAllowed,
        updatedAt: Date.now(),
    };
    },
    addFiles(files) {
      if (fileAdditionLock.current) {
        setFeedback("FILE_SELECTION_IN_PROGRESS");
        return;
    }
    const fileOwner = fileAdditionOwner.current + 1;
    fileAdditionOwner.current = fileOwner;
    fileAdditionLock.current = true;
    try {
        let identityGuard;
        try {
            identityGuard = captureIntakeIdentity();
        }
        catch (error) {
            setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
            return;
        }
        const selectedFiles = [];
        let selectedBytes = 0;
        for (const file of files) {
            if (selectionCapacity.current.count + selectedFiles.length >= maximumBatchAssets) {
                setFeedback("BATCH_ASSET_COUNT_LIMIT_EXCEEDED");
                return;
            }
            selectedBytes += file.size;
            if (!Number.isSafeInteger(file.size)
                || file.size < 0
                || !Number.isSafeInteger(selectedBytes)
                || selectionCapacity.current.bytes + selectedBytes > maximumBatchBytes) {
                setFeedback("BATCH_BYTE_LIMIT_EXCEEDED");
                return;
            }
            selectedFiles.push(file);
        }
        if (selectedFiles.length === 0)
            return;
        if (!await ensureRecoveryStore()) {
            if (intakeIdentityIsCurrent(identityGuard))
                setFeedback("RECOVERY_STORE_UNAVAILABLE");
            return;
        }
        assertIntakeIdentityCurrent(identityGuard);
        let fingerprinted;
        try {
            fingerprinted = await Promise.all(selectedFiles.map(async (file) => ({ file, fingerprint: await fingerprintFile(file) })));
            assertIntakeIdentityCurrent(identityGuard);
        }
        catch (_error) {
            if (intakeIdentityIsCurrent(identityGuard))
                setFeedback("FILE_FINGERPRINT_FAILED");
            return;
        }
        const invalidRecoveryFingerprints = new Set();
        for (const { file, fingerprint } of fingerprinted) {
            for (const record of recoveryRecords(projectId, fingerprint)) {
                if (record.expectedSize !== file.size
                    || record.lastModified !== file.lastModified
                    || record.partSize !== chunkBytes) {
                    try {
                        await clearRecovery(record, identityGuard);
                    }
                    catch (_error) {
                        if (intakeIdentityIsCurrent(identityGuard)) {
                            setFeedback("RECOVERY_STORE_WRITE_FAILED");
                        }
                        return;
                    }
                    invalidRecoveryFingerprints.add(fingerprint);
                }
            }
        }
        const batchFingerprintCounts = new Map();
        for (const { fingerprint } of fingerprinted) {
            batchFingerprintCounts.set(fingerprint, (batchFingerprintCounts.get(fingerprint) ?? 0) + 1);
        }
        const existingFingerprints = new Set(assets.map((asset) => asset.fileFingerprint));
        const collisionFingerprints = new Set(fingerprinted
            .map(({ fingerprint }) => fingerprint)
            .filter((fingerprint) => (batchFingerprintCounts.get(fingerprint) ?? 0) > 1 || existingFingerprints.has(fingerprint)));
        const hasCollision = collisionFingerprints.size > 0;
        assertIntakeIdentityCurrent(identityGuard);
        if (hasCollision)
            setFeedback("FILE_FINGERPRINT_COLLISION");
        selectionCapacity.current = {
            count: selectionCapacity.current.count + fingerprinted.length,
            bytes: selectionCapacity.current.bytes + selectedBytes,
        };
        setAssets((current) => {
            const protectedCurrent = current.map((asset) => collisionFingerprints.has(asset.fileFingerprint)
                ? {
                    ...asset,
                    phase: "BLOCKED",
                    progress: 100,
                    permanentBlock: true,
                    recoveryCandidate: false,
                    recoveryAttached: false,
                    code: "FILE_FINGERPRINT_COLLISION",
                }
                : asset);
            const additions = fingerprinted
                .map(({ file, fingerprint }, index) => {
                const collision = collisionFingerprints.has(fingerprint);
                const recoveries = collision ? [] : recoveryRecords(projectId, fingerprint);
                const code = invalidRecoveryFingerprints.has(fingerprint)
                    ? "RECOVERY_METADATA_MISMATCH"
                    : file.size <= 0
                        ? "EMPTY_FILE_NOT_ALLOWED"
                        : file.size > maximumProcessableAssetBytes
                            ? "FILE_EXCEEDS_64_MIB_PROCESSING_LIMIT"
                            : collision
                                ? "FILE_FINGERPRINT_COLLISION"
                                : supportedExtensions.has(extensionOf(file))
                                    ? undefined
                                    : "FILE_TYPE_NOT_IN_V1_ALLOWLIST";
                return {
                    key: `${fingerprint}:${index}:${crypto.randomUUID()}`,
                    fileFingerprint: fingerprint,
                    attemptKey: crypto.randomUUID(),
                    projectId: recoveries.length > 0 ? projectId : undefined,
                    file,
                    relativePath: relativePath(file),
                    phase: code ? "BLOCKED" : "SELECTED",
                    progress: 0,
                    permanentBlock: Boolean(code),
                    recoveryCandidate: recoveries.length > 0,
                    recoveryAttached: false,
                    confirmedPartCount: 0,
                    processingAttempt: 0,
                    role: recoveries[0]?.role ?? "PRIMARY",
                    modelReadAllowed: recoveries[0]?.modelReadAllowed ?? true,
                    code,
                };
            });
            return [...protectedCurrent, ...additions];
        });
    }
    catch (error) {
        // A scope change mid-addition discards the selection. Report it instead of
        // dropping the files silently: the file input value is already cleared, so
        // nothing retries on its own.
        setFeedback(error instanceof Error ? error.message : "FILE_SELECTION_FAILED");
    }
    finally {
        if (fileAdditionOwner.current === fileOwner)
            fileAdditionLock.current = false;
    }
    },
    update(key, patch) {
      setAssets((current) => current.map((asset) => asset.key === key ? { ...asset, ...patch } : asset));
    },
    updateMany(keys, patch) {
      const selected = new Set(keys);
    setAssets((current) => current.map((asset) => selected.has(asset.key) ? { ...asset, ...patch } : asset));
    },
    refreshProcessingEstimate() {
      if (!safeProject(projectId) || estimatePlan.stages.length === 0) {
        setEstimate({
            inputDigest: "",
            status: "BLOCKED",
            code: "ESTIMATION_STAGES_REQUIRED",
        });
        return;
    }
    let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setEstimate({
            inputDigest: "",
            status: "BLOCKED",
            code: error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE",
        });
        return;
    }
    const owner = estimateRequestOwner.current + 1;
    estimateRequestOwner.current = owner;
    setEstimateBusy(true);
    setEstimate(null);
    try {
        const inputDigest = await sha256(new TextEncoder().encode(estimatePlanDocument).buffer);
        if (owner !== estimateRequestOwner.current)
            return;
        assertIntakeIdentityCurrent(identityGuard);
        const response = await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-processing-cost-and-eta-estimation", "estimate", estimatePlan, `mmi-cost-estimate-${inputDigest.slice(0, 40)}`);
        if (owner !== estimateRequestOwner.current)
            return;
        setEstimate(processingEstimate(response, `sha256:${inputDigest}`));
    }
    catch (error) {
        if (owner !== estimateRequestOwner.current || !intakeIdentityIsCurrent(identityGuard))
            return;
        const failure = failureDetails(error, "PROCESSING_ESTIMATE_FAILED");
        setEstimate({
            inputDigest: "",
            status: "BLOCKED",
            code: failure.code,
        });
    }
    finally {
        if (owner === estimateRequestOwner.current)
            setEstimateBusy(false);
    }
    },
    uploadAsset(asset, sessionId, projectAlias, identityGuard) {
      assertIntakeIdentityCurrent(identityGuard);
    if (asset.permanentBlock)
        throw new Error(asset.code ?? "ASSET_PERMANENTLY_BLOCKED");
    if (asset.sessionId && asset.sessionId !== sessionId)
        throw new Error("INPUT_SESSION_ID_CHANGED");
    if (asset.projectId !== projectAlias)
        throw new Error("ASSET_PROJECT_BINDING_MISMATCH");
    update(asset.key, {
        sessionId,
        phase: "HASHING",
        progress: 2,
        code: undefined,
        response: undefined,
        traceId: undefined,
    });
    const digest = await sha256FileOffMainThread(asset.file);
    assertIntakeIdentityCurrent(identityGuard);
    if (asset.sha256 && asset.sha256 !== digest) {
        await clearRecovery(asset, identityGuard);
        throw new Error("RECOVERY_CONTENT_HASH_MISMATCH");
    }
    update(asset.key, { sha256: digest, phase: "UPLOADING", progress: 5 });
    let recoveryAsset = { ...asset, sessionId, sha256: digest };
    await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
    if (recoveryAsset.assetId) {
        update(asset.key, { phase: "PROCESSING", progress: 78 });
        return recoveryAsset.assetId;
    }
    const started = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-secure-resumable-upload", "start", {
        session_id: sessionId,
        display_name: asset.relativePath,
        expected_size: asset.file.size,
        expected_sha256: digest,
        declared_media_type: asset.file.type || "application/octet-stream",
        part_size: chunkBytes,
    }, `mmi-${asset.attemptKey}-start`);
    const uploadSessionId = responseString(started, "upload_session_id", "session_id", "upload_id");
    if (!uploadSessionId)
        throw new Error("UPLOAD_SESSION_ID_MISSING");
    if (asset.uploadSessionId && asset.uploadSessionId !== uploadSessionId) {
        throw new Error("UPLOAD_SESSION_ID_CHANGED");
    }
    update(asset.key, { uploadSessionId });
    recoveryAsset = { ...recoveryAsset, uploadSessionId };
    await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
    const partCount = Math.max(1, Math.ceil(asset.file.size / chunkBytes));
    if (recoveryAsset.confirmedPartCount > partCount) {
        await clearRecovery(recoveryAsset, identityGuard);
        throw new Error("RECOVERY_CONFIRMED_PROGRESS_INVALID");
    }
    for (let part = recoveryAsset.confirmedPartCount; part < partCount; part += 1) {
        const start = part * chunkBytes;
        const chunk = new Uint8Array(await asset.file.slice(start, Math.min(asset.file.size, start + chunkBytes)).arrayBuffer());
        const chunkDigest = await sha256(chunk.slice().buffer);
        assertIntakeIdentityCurrent(identityGuard);
        await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-secure-resumable-upload", "upload_part", {
            upload_session_id: uploadSessionId,
            part_number: part,
            byte_offset: start,
            sha256: chunkDigest,
            data_b64: bytesToBase64(chunk),
        }, `mmi-${asset.attemptKey}-part-${part + 1}`);
        recoveryAsset = { ...recoveryAsset, confirmedPartCount: part + 1 };
        await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
        update(asset.key, {
            confirmedPartCount: part + 1,
            progress: 5 + Math.round(((part + 1) / partCount) * 60),
        });
    }
    update(asset.key, { phase: "VALIDATING", progress: 70 });
    const committed = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-secure-resumable-upload", "commit", { upload_session_id: uploadSessionId, expected_sha256: digest }, `mmi-${asset.attemptKey}-commit`);
    const assetId = responseString(committed, "asset_id", "asset_version_id", "object_id");
    if (!assetId)
        throw new Error("ASSET_ID_MISSING");
    if (asset.assetId && asset.assetId !== assetId)
        throw new Error("ASSET_ID_CHANGED");
    const committedAsset = outputRecord(committed, "asset");
    const assetVersion = positiveInteger(committedAsset?.version) ?? asset.assetVersion;
    recoveryAsset = { ...recoveryAsset, assetId, assetVersion };
    await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
    update(asset.key, {
        assetId,
        assetVersion,
        phase: "PROCESSING",
        progress: 78,
    });
    return assetId;
    },
    processAll() {
      let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    if (!recoveryStoreReady && !await ensureRecoveryStore()) {
        if (intakeIdentityIsCurrent(identityGuard))
            setFeedback("RECOVERY_STORE_UNAVAILABLE");
        return;
    }
    assertIntakeIdentityCurrent(identityGuard);
    if (!safeProject(projectId)) {
        setFeedback("项目 ID 仅允许字母、数字、点、下划线、冒号和短横线。");
        return;
    }
    const fingerprintCounts = new Map();
    for (const asset of assets) {
        fingerprintCounts.set(asset.fileFingerprint, (fingerprintCounts.get(asset.fileFingerprint) ?? 0) + 1);
    }
    const duplicateFingerprints = new Set([...fingerprintCounts]
        .filter(([, count]) => count > 1)
        .map(([fingerprint]) => fingerprint));
    if (duplicateFingerprints.size > 0) {
        setAssets((current) => current.map((asset) => duplicateFingerprints.has(asset.fileFingerprint)
            ? {
                ...asset,
                phase: "BLOCKED",
                progress: 100,
                permanentBlock: true,
                recoveryCandidate: false,
                recoveryAttached: false,
                code: "FILE_FINGERPRINT_COLLISION",
            }
            : asset));
        setFeedback("FILE_FINGERPRINT_COLLISION");
        return;
    }
    const projectAlias = projectId;
    const retryable = assets.filter((asset) => !asset.permanentBlock
        && asset.role !== "IGNORE"
        && asset.modelReadAllowed
        && ["SELECTED", "BLOCKED", "NEEDS_REVIEW"].includes(asset.phase));
    if (retryable.length === 0) {
        setFeedback("没有可接入或可恢复的条目；永久阻断的空文件、超限文件和不支持格式不会重试。");
        return;
    }
    if (retryable.some((asset) => asset.projectId && asset.projectId !== projectAlias)) {
        setFeedback("ASSET_PROJECT_BINDING_MISMATCH");
        return;
    }
    const busyOwner = intakeBusyOwner.current + 1;
    intakeBusyOwner.current = busyOwner;
    setBusy(true);
    setFeedback("");
    const newSessionAttemptKey = crypto.randomUUID();
    let candidates = retryable.map((asset) => {
        return {
            ...asset,
            projectId: asset.projectId ?? projectAlias,
            sessionAttemptKey: asset.sessionAttemptKey
                ?? newSessionAttemptKey,
        };
    });
    const newlyAssigned = retryable
        .filter((asset) => !asset.sessionAttemptKey && !asset.recoveryCandidate)
        .map((asset) => asset.key);
    if (newlyAssigned.length > 0) {
        updateMany(newlyAssigned, { projectId: projectAlias, sessionAttemptKey: newSessionAttemptKey });
    }
    const missingProjectBinding = retryable
        .filter((asset) => asset.sessionAttemptKey && !asset.projectId)
        .map((asset) => asset.key);
    if (missingProjectBinding.length > 0)
        updateMany(missingProjectBinding, { projectId: projectAlias });
    const bootstrapAttemptKey = candidates[0].sessionAttemptKey;
    if (!bootstrapAttemptKey) {
        setFeedback("INPUT_SESSION_ATTEMPT_KEY_MISSING");
        setBusy(false);
        return;
    }
    try {
        let engineProjectId = "";
        try {
            const bootstrapped = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-multimodal-input-orchestrator", "bootstrap_project", {}, `mmi-${bootstrapAttemptKey}-bootstrap`);
            engineProjectId = responseString(bootstrapped, "project_id", "engine_project_id") ?? "";
            if (!boundedOpaque(engineProjectId))
                throw new Error("ENGINE_PROJECT_SCOPE_MISSING");
        }
        catch (error) {
            if (!intakeIdentityIsCurrent(identityGuard))
                return;
            const failure = failureDetails(error, "PROJECT_BOOTSTRAP_FAILED");
            updateMany(candidates.map((asset) => asset.key), {
                phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
                progress: 100,
                permanentBlock: failure.quarantined,
                code: failure.code,
                traceId: failure.traceId,
                response: failure.payload,
            });
            setFeedback(failure.code);
            return;
        }
        const scopeMismatches = candidates.filter((asset) => {
            if (!asset.recoveryCandidate && !asset.recoveryAttached)
                return false;
            return recoveryRecords(projectAlias, asset.fileFingerprint, engineProjectId).length !== 1;
        });
        if (scopeMismatches.length > 0) {
            const mismatchedKeys = new Set(scopeMismatches.map((asset) => asset.key));
            for (const asset of candidates) {
                if (!mismatchedKeys.has(asset.key)) {
                    update(asset.key, {
                        phase: "BLOCKED",
                        progress: 100,
                        code: "RECOVERY_BATCH_ENGINE_PROJECT_SCOPE_MISMATCH",
                    });
                    continue;
                }
                update(asset.key, {
                    attemptKey: crypto.randomUUID(),
                    engineProjectId: undefined,
                    sessionAttemptKey: undefined,
                    sessionId: undefined,
                    sha256: undefined,
                    uploadSessionId: undefined,
                    confirmedPartCount: 0,
                    processingAttempt: 0,
                    assetId: undefined,
                    assetVersion: undefined,
                    phase: "BLOCKED",
                    progress: 100,
                    permanentBlock: true,
                    recoveryCandidate: false,
                    recoveryAttached: false,
                    code: "RECOVERY_ENGINE_PROJECT_SCOPE_MISMATCH",
                });
            }
            setFeedback("RECOVERY_ENGINE_PROJECT_SCOPE_MISMATCH");
            return;
        }
        candidates = candidates.map((asset) => {
            const recovery = asset.recoveryCandidate || asset.recoveryAttached
                ? recoveryRecords(projectAlias, asset.fileFingerprint, engineProjectId)[0]
                : undefined;
            return {
                ...asset,
                attemptKey: recovery?.attemptKey ?? asset.attemptKey,
                projectId: recovery?.projectId ?? asset.projectId,
                engineProjectId,
                sessionAttemptKey: recovery?.sessionAttemptKey ?? asset.sessionAttemptKey,
                sessionId: recovery?.sessionId ?? asset.sessionId,
                confirmedPartCount: recovery?.confirmedPartCount ?? asset.confirmedPartCount,
                sha256: recovery?.contentSha256 ?? asset.sha256,
                uploadSessionId: recovery?.uploadSessionId ?? asset.uploadSessionId,
                assetId: recovery?.assetId ?? asset.assetId,
                assetVersion: recovery?.assetVersion ?? asset.assetVersion,
                role: recovery?.role ?? asset.role,
                modelReadAllowed: recovery?.modelReadAllowed ?? asset.modelReadAllowed,
                processingAttempt: recovery?.processingAttempt ?? asset.processingAttempt,
                recoveryCandidate: false,
                recoveryAttached: true,
            };
        });
        const claimedAssetIds = new Map();
        const identityCollisionKeys = new Set();
        for (const asset of [...assets, ...candidates]) {
            if (!asset.assetId)
                continue;
            const owner = claimedAssetIds.get(asset.assetId);
            if (owner && owner !== asset.key) {
                identityCollisionKeys.add(owner);
                identityCollisionKeys.add(asset.key);
                continue;
            }
            claimedAssetIds.set(asset.assetId, asset.key);
        }
        if (identityCollisionKeys.size > 0) {
            updateMany([...identityCollisionKeys], {
                phase: "BLOCKED",
                progress: 100,
                permanentBlock: true,
                recoveryCandidate: false,
                recoveryAttached: false,
                code: "ASSET_IDENTITY_COLLISION",
            });
            setFeedback("ASSET_IDENTITY_COLLISION");
            return;
        }
        try {
            for (const asset of candidates) {
                await persistRecovery(recoveryFromAsset(asset, identityGuard), identityGuard);
                const partCount = Math.max(1, Math.ceil(asset.file.size / chunkBytes));
                update(asset.key, {
                    attemptKey: asset.attemptKey,
                    projectId: asset.projectId,
                    engineProjectId,
                    sessionAttemptKey: asset.sessionAttemptKey,
                    sessionId: asset.sessionId,
                    sha256: asset.sha256,
                    uploadSessionId: asset.uploadSessionId,
                    confirmedPartCount: asset.confirmedPartCount,
                    processingAttempt: asset.processingAttempt,
                    assetId: asset.assetId,
                    assetVersion: asset.assetVersion,
                    recoveryCandidate: false,
                    recoveryAttached: true,
                    progress: Math.min(69, 5 + Math.round((asset.confirmedPartCount / partCount) * 60)),
                });
            }
        }
        catch (error) {
            if (!intakeIdentityIsCurrent(identityGuard))
                return;
            const failure = failureDetails(error, "RECOVERY_STORE_WRITE_FAILED");
            updateMany(candidates.map((asset) => asset.key), {
                phase: "BLOCKED",
                progress: 100,
                code: failure.code,
                traceId: failure.traceId,
                response: failure.payload,
            });
            setFeedback(failure.code);
            return;
        }
        const grouped = new Map();
        for (const asset of candidates) {
            const sessionAttemptKey = asset.sessionAttemptKey;
            if (!sessionAttemptKey)
                continue;
            const groupKey = asset.sessionId
                ? `session:${asset.sessionId}`
                : `attempt:${sessionAttemptKey}:${asset.role}`;
            const group = grouped.get(groupKey) ?? {
                sessionAttemptKey,
                sessionId: asset.sessionId,
                role: asset.role,
                assets: [],
            };
            if (group.role !== asset.role)
                throw new Error("SESSION_ROLE_SCOPE_MISMATCH");
            group.assets.push(asset);
            grouped.set(groupKey, group);
        }
        const resolved = [];
        for (const group of grouped.values()) {
            try {
                let sessionId = group.sessionId;
                if (!sessionId) {
                    const created = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-multimodal-input-orchestrator", "create_session", { requested_role: group.role }, `mmi-${group.sessionAttemptKey}-session`);
                    sessionId = responseString(created, "session_id") ?? "";
                    if (!sessionId)
                        throw new Error("INPUT_SESSION_ID_MISSING");
                    updateMany(group.assets.map((asset) => asset.key), { sessionId });
                    for (const asset of group.assets) {
                        await persistRecovery(recoveryFromAsset({ ...asset, sessionId }, identityGuard), identityGuard);
                    }
                }
                resolved.push({
                    sessionAttemptKey: group.sessionAttemptKey,
                    sessionId,
                    assets: group.assets.map((asset) => ({ ...asset, sessionId })),
                });
            }
            catch (error) {
                if (!intakeIdentityIsCurrent(identityGuard))
                    return;
                const failure = failureDetails(error, "INPUT_SESSION_CREATION_FAILED");
                updateMany(group.assets.map((asset) => asset.key), {
                    phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
                    progress: 100,
                    permanentBlock: failure.quarantined,
                    code: failure.code,
                    traceId: failure.traceId,
                    response: failure.payload,
                });
            }
        }
        const uploadedGroups = [];
        for (const group of resolved) {
            const uploaded = new Map();
            for (const asset of group.assets) {
                try {
                    const assetId = await uploadAsset(asset, group.sessionId, projectAlias, identityGuard);
                    const owner = claimedAssetIds.get(assetId);
                    if (owner && owner !== asset.key) {
                        identityCollisionKeys.add(owner);
                        identityCollisionKeys.add(asset.key);
                        continue;
                    }
                    claimedAssetIds.set(assetId, asset.key);
                    uploaded.set(asset.key, assetId);
                }
                catch (error) {
                    if (!intakeIdentityIsCurrent(identityGuard))
                        return;
                    const failure = failureDetails(error, "UPLOAD_FAILED");
                    const recoveryInvalid = [
                        "RECOVERY_CONTENT_HASH_MISMATCH",
                        "RECOVERY_CONFIRMED_PROGRESS_INVALID",
                        "RECOVERY_METADATA_INVALID",
                    ].includes(failure.code);
                    const permanentlyBlocked = failure.quarantined || recoveryInvalid || failure.retryable === false;
                    update(asset.key, {
                        phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
                        progress: 100,
                        permanentBlock: permanentlyBlocked,
                        recoveryCandidate: false,
                        recoveryAttached: permanentlyBlocked ? false : asset.recoveryAttached,
                        ...(recoveryInvalid ? {
                            engineProjectId: undefined,
                            sessionAttemptKey: undefined,
                            sessionId: undefined,
                            sha256: undefined,
                            uploadSessionId: undefined,
                            confirmedPartCount: 0,
                            processingAttempt: 0,
                            assetId: undefined,
                            assetVersion: undefined,
                        } : {}),
                        code: failure.code,
                        traceId: failure.traceId,
                        response: failure.payload,
                    });
                }
            }
            if (uploaded.size > 0)
                uploadedGroups.push({ group, uploaded });
        }
        if (identityCollisionKeys.size > 0) {
            updateMany([...identityCollisionKeys], {
                phase: "BLOCKED",
                progress: 100,
                permanentBlock: true,
                recoveryCandidate: false,
                recoveryAttached: false,
                code: "ASSET_IDENTITY_COLLISION",
            });
            setFeedback("ASSET_IDENTITY_COLLISION");
            return;
        }
        for (const { group, uploaded } of uploadedGroups) {
            try {
                const committedAssetIds = new Set(assets
                    .filter((asset) => asset.sessionId === group.sessionId && asset.assetId)
                    .map((asset) => asset.assetId));
                for (const assetId of uploaded.values())
                    committedAssetIds.add(assetId);
                const membership = [...committedAssetIds].sort().join("\n");
                const membershipDigest = await sha256(new TextEncoder().encode(membership).buffer);
                assertIntakeIdentityCurrent(identityGuard);
                const processingAttempt = Math.max(0, ...group.assets.map((asset) => asset.processingAttempt));
                const processed = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-multimodal-input-orchestrator", "process_session", {
                    session_id: group.sessionId,
                    max_attempts: 3,
                    expected_asset_generation_digest: membershipDigest,
                }, `mmi-${group.sessionAttemptKey}-process-${membershipDigest.slice(0, 32)}-${processingAttempt}`);
                const output = nestedRecord(processed);
                const processingJobId = responseString(processed, "job_id");
                if (!processingJobId
                    || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(processingJobId))
                    throw new Error("WORKFLOW_JOB_ID_MISSING");
                const processedAssets = Array.isArray(output.assets) ? output.assets : [];
                const assetsTruncated = output.assets_truncated === true;
                const resultById = new Map();
                for (const item of processedAssets) {
                    if (item && typeof item === "object" && !Array.isArray(item)) {
                        const entry = item;
                        if (typeof entry.asset_id === "string") {
                            if (resultById.has(entry.asset_id)) {
                                throw new Error("WORKFLOW_DUPLICATE_ASSET_ID");
                            }
                            resultById.set(entry.asset_id, entry);
                        }
                    }
                }
                for (const [key, assetId] of uploaded) {
                    const assetResult = resultById.get(assetId);
                    const assetStatus = assetResult?.status;
                    const assetVersion = positiveInteger(assetResult?.version);
                    const phase = assetResult
                        ? typeof assetStatus === "string"
                            ? phaseFrom({ status: assetStatus })
                            : "NEEDS_REVIEW"
                        : "NEEDS_REVIEW";
                    const assetCode = assetResult
                        ? responseString(assetResult, "failure_code", "error_code", "code")
                        : undefined;
                    const terminal = ["READY", "QUARANTINED"].includes(phase);
                    const nextProcessingAttempt = processingAttempt + 1;
                    update(key, {
                        phase,
                        progress: 100,
                        permanentBlock: phase === "QUARANTINED",
                        recoveryAttached: !terminal,
                        processingAttempt: terminal ? processingAttempt : nextProcessingAttempt,
                        processingJobId: terminal ? undefined : processingJobId,
                        ...(assetVersion ? { assetVersion } : {}),
                        response: processed,
                        traceId: responseString(processed, "trace_id"),
                        code: phase === "READY"
                            ? undefined
                            : !assetResult
                                ? assetsTruncated
                                    ? "WORKFLOW_ASSET_SUMMARY_TRUNCATED"
                                    : "WORKFLOW_ASSET_RESULT_MISSING"
                                : assetCode ?? responseString(processed, "code", "error_code"),
                    });
                    const completedAsset = group.assets.find((asset) => asset.key === key);
                    if (terminal && completedAsset) {
                        await clearRecovery(completedAsset, identityGuard);
                    }
                    else if (completedAsset) {
                        if (!completedAsset.engineProjectId) {
                            throw new Error("RECOVERY_PROCESSING_SCOPE_MISSING");
                        }
                        const records = recoveryRecords(projectAlias, completedAsset.fileFingerprint, completedAsset.engineProjectId);
                        if (records.length !== 1)
                            throw new Error("RECOVERY_PROCESSING_STATE_MISSING");
                        await persistRecovery({
                            ...records[0],
                            processingAttempt: nextProcessingAttempt,
                            ...(assetVersion ? { assetVersion } : {}),
                            updatedAt: Date.now(),
                        }, identityGuard);
                    }
                }
            }
            catch (error) {
                if (!intakeIdentityIsCurrent(identityGuard))
                    return;
                const failure = failureDetails(error, "SESSION_PROCESSING_FAILED");
                const workflowIntegrityFailure = [
                    "WORKFLOW_DUPLICATE_ASSET_ID",
                    "RECOVERY_PROCESSING_STATE_MISSING",
                    "RECOVERY_PROCESSING_SCOPE_MISSING",
                ].includes(failure.code);
                updateMany([...uploaded.keys()], {
                    phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
                    progress: 100,
                    permanentBlock: failure.quarantined || workflowIntegrityFailure,
                    code: failure.code,
                    traceId: failure.traceId,
                    response: failure.payload,
                });
            }
        }
    }
    finally {
        if (intakeBusyOwner.current === busyOwner)
            setBusy(false);
    }
    },
    addDirectText() {
      const value = directText.trim();
    if (!value)
        return;
    const file = new File([value], `direct-input-${Date.now()}.md`, {
        type: "text/markdown;charset=utf-8",
        lastModified: Date.now(),
    });
    void addFiles([file]);
    setDirectText("");
    },
    buildPackagePreview() {
      if (!safeProject(projectId) || assets.length === 0)
        return;
    let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const busyOwner = intakeBusyOwner.current + 1;
    intakeBusyOwner.current = busyOwner;
    setBusy(true);
    setFeedback("");
    try {
        if (assets.some((asset) => asset.file.size <= 0 || asset.file.size > maximumProcessableAssetBytes)) {
            throw new Error("PREVIEW_REQUIRES_BOUNDED_NON_EMPTY_ASSETS");
        }
        const previewAssets = [];
        for (const asset of assets) {
            const digest = asset.sha256 ?? await sha256FileOffMainThread(asset.file);
            assertIntakeIdentityCurrent(identityGuard);
            if (!/^[0-9a-f]{64}$/.test(digest))
                throw new Error("PREVIEW_CONTENT_DIGEST_INVALID");
            if (asset.sha256 && asset.sha256 !== digest) {
                throw new Error("PREVIEW_CONTENT_DIGEST_MISMATCH");
            }
            if (!asset.sha256)
                update(asset.key, { sha256: digest });
            previewAssets.push({ ...asset, sha256: digest });
        }
        const previewScopeDigest = await sha256(new TextEncoder().encode(`preview-bootstrap\u0000${projectId}`).buffer);
        assertIntakeIdentityCurrent(identityGuard);
        await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-multimodal-input-orchestrator", "bootstrap_project", {}, `mmi-preview-bootstrap-${previewScopeDigest.slice(0, 40)}`);
        const entries = previewAssets.map((asset) => ({
            path: asset.relativePath,
            kind: "file",
            byte_count: asset.file.size,
            content_digest: `sha256:${asset.sha256}`,
            role: asset.role,
            model_read_allowed: asset.modelReadAllowed && asset.phase === "READY",
            metadata: {
                ...(asset.assetId ? { asset_id: asset.assetId } : {}),
                intake_state: asset.phase,
            },
        }));
        const packageSessionId = `package-${crypto.randomUUID()}`;
        await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-folder-tree-input", "begin", { session_id: packageSessionId, expected_entry_count: entries.length }, `mmi-package-begin-${packageSessionId}`);
        for (let offset = 0, chunkIndex = 0; offset < entries.length; offset += 1_000, chunkIndex += 1) {
            await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-folder-tree-input", "append", { session_id: packageSessionId, chunk_index: chunkIndex, entries: entries.slice(offset, offset + 1_000) }, `mmi-package-append-${packageSessionId}-${chunkIndex}`);
        }
        const finalized = await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-folder-tree-input", "finalize", { session_id: packageSessionId }, `mmi-package-finalize-${packageSessionId}`);
        const packageVersion = nestedRecord(finalized).package_version;
        if (!Number.isSafeInteger(packageVersion) || Number(packageVersion) < 1) {
            throw new Error("PROJECT_PACKAGE_VERSION_INVALID");
        }
        const firstPage = await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-project-package-preview-and-review-ui", "page", { package_version: packageVersion, limit: 100 }, `mmi-package-page-${packageSessionId}-0`);
        setPackagePreview(finalized);
        setPackagePage(projectPackagePage(firstPage));
        setPackagePageCursors([null]);
        setPackagePageIndex(0);
    }
    catch (error) {
        if (intakeIdentityIsCurrent(identityGuard)) {
            setFeedback(error instanceof Error ? error.message : "PACKAGE_PREVIEW_FAILED");
        }
    }
    finally {
        if (intakeBusyOwner.current === busyOwner)
            setBusy(false);
    }
    },
    loadPackagePage(cursor, targetIndex) {
      if (!packagePage || targetIndex < 0 || !safeProject(projectId))
        return;
    let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const busyOwner = intakeBusyOwner.current + 1;
    intakeBusyOwner.current = busyOwner;
    setBusy(true);
    setFeedback("");
    try {
        const response = await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-project-package-preview-and-review-ui", "page", {
            package_version: packagePage.package_version,
            limit: 100,
            ...(cursor ? { cursor } : {}),
        }, `mmi-package-page-${packagePage.collection_digest}-${targetIndex}-${crypto.randomUUID()}`);
        const page = projectPackagePage(response);
        if (page.package_version !== packagePage.package_version
            || page.collection_digest !== packagePage.collection_digest)
            throw new Error("PROJECT_PACKAGE_PAGE_DRIFT");
        setPackagePage(page);
        setPackagePageIndex(targetIndex);
    }
    catch (error) {
        if (intakeIdentityIsCurrent(identityGuard)) {
            setFeedback(error instanceof Error ? error.message : "PROJECT_PACKAGE_PAGE_FAILED");
        }
    }
    finally {
        if (intakeBusyOwner.current === busyOwner)
            setBusy(false);
    }
    },
    selectedReviewTask() {
      return reviewTasks.find((task) => task.task_id === selectedReviewTaskId);
    },
    beginReviewRequest() {
      const guard = {
        generation: reviewScopeGeneration.current,
        owner: reviewRequestOwner.current + 1,
        projectId,
        identityScope: reviewIdentityScope,
    };
    reviewRequestOwner.current = guard.owner;
    setReviewBusy(true);
    return guard;
    },
    reviewRequestIsCurrent(guard) {
      return guard.generation === reviewScopeGeneration.current
        && guard.owner === reviewRequestOwner.current;
    },
    assertReviewRequestCurrent(guard) {
      if (!reviewRequestIsCurrent(guard))
    throw new Error("HUMAN_REVIEW_SCOPE_CHANGED");
    },
    finishReviewRequest(guard) {
      if (reviewRequestIsCurrent(guard))
    setReviewBusy(false);
    },
    executeGuardedReviewSkill(guard, skill, operation, input, idempotencyKey) {
      assertReviewRequestCurrent(guard);
    const response = await executeSkill(guard.projectId, skill, operation, input, idempotencyKey);
    assertReviewRequestCurrent(guard);
    return response;
    },
    saveReviewClaim(claim) {
      if (!reviewIdentityScope || claim.identity_scope !== reviewIdentityScope)
        return false;
    const next = Object.fromEntries(Object.entries(reviewClaims).filter(([, value]) => (validReviewClaim(value, reviewIdentityScope))));
    next[claim.task_id] = claim;
    if (!persistReviewClaims(next, reviewIdentityScope))
        return false;
    setReviewClaims(next);
    return true;
    },
    discardReviewClaim(taskId) {
      if (!reviewIdentityScope)
        return false;
    const next = Object.fromEntries(Object.entries(reviewClaims).filter(([candidateId, value]) => (candidateId !== taskId && validReviewClaim(value, reviewIdentityScope))));
    if (!persistReviewClaims(next, reviewIdentityScope))
        return false;
    setReviewClaims(next);
    return true;
    },
    abandonReviewClaimRecovery(taskId) {
      if (!discardReviewClaim(taskId)) {
        setFeedback("HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED");
        return;
    }
    setReviewTasks((current) => current.filter((task) => task.task_id !== taskId));
    setSelectedReviewTaskId("");
    setFeedback("本地领取恢复已清除；请刷新队列后按最新任务版本重新领取。");
    },
    reconcileReviewClaims(tasks) {
      if (!reviewIdentityScope)
        return;
    const next = { ...reviewClaims };
    let changed = false;
    for (const [taskId, claim] of Object.entries(next)) {
        if (!validReviewClaim(claim, reviewIdentityScope)) {
            delete next[taskId];
            changed = true;
            continue;
        }
        if (claim.project_id !== projectId)
            continue;
        const task = tasks.find((candidate) => candidate.task_id === taskId);
        const closed = task && ["APPROVED", "REJECTED", "REVERTING", "REVERTED"].includes(task.state);
        const fencedDrift = task && claim.fence !== undefined && (task.claim_fence !== claim.fence
            || task.claim_expires_at !== claim.expires_at
            || !["CLAIMED", "EDITED"].includes(task.state));
        // A pending receipt is the only durable handle for replaying a claim
        // whose response was lost.  List state is observational: CLAIMED vN+1
        // can mean this exact request committed.  Preserve the original key and
        // token until the server gives a definitive conflict or the bounded
        // recovery window expires.
        if (!task || closed || fencedDrift) {
            delete next[taskId];
            changed = true;
        }
    }
    if (changed && persistReviewClaims(next, reviewIdentityScope)) {
        setReviewClaims(next);
    }
    },
    validatedReviewTask(response, guard, expected) {
      assertReviewRequestCurrent(guard);
    const task = reviewTask(outputRecord(response, "task"), reviewEngineScope.current);
    if (!task)
        throw new Error("HUMAN_REVIEW_TASK_RESPONSE_INVALID");
    if (expected.priorTask) {
        const immutable = (candidate) => ({
            tenant_id: candidate.tenant_id,
            project_id: candidate.project_id,
            created_by: candidate.created_by,
            asset_id: candidate.asset_id,
            target_kind: candidate.target_kind,
            target: candidate.target,
            original_value: candidate.original_value,
            source_digest: candidate.source_digest,
            source_ref: candidate.source_ref,
            confidence: candidate.confidence,
            reason: candidate.reason,
            created_at: candidate.created_at,
        });
        if (!expected.priorTask.detail_loaded
            || !task.detail_loaded
            || canonicalStrictJson(immutable(task))
                !== canonicalStrictJson(immutable(expected.priorTask))
            || task.version < expected.priorTask.version
            || task.version === expected.priorTask.version
                && canonicalStrictJson(reviewTaskDynamicState(task))
                    !== canonicalStrictJson(reviewTaskDynamicState(expected.priorTask)))
            throw new Error("HUMAN_REVIEW_TASK_IMMUTABLE_BINDING_INVALID");
    }
    if (expected.taskId !== undefined && task.task_id !== expected.taskId
        || expected.assetId !== undefined && task.asset_id !== expected.assetId
        || expected.targetKind !== undefined && task.target_kind !== expected.targetKind
        || expected.target !== undefined && (task.target === undefined
            || canonicalStrictJson(task.target) !== canonicalStrictJson(expected.target))
        || expected.bindOriginalValue === true && (!Object.hasOwn(task, "original_value")
            || canonicalStrictJson(task.original_value) !== canonicalStrictJson(expected.originalValue))
        || expected.state !== undefined && task.state !== expected.state
        || expected.version !== undefined && task.version !== expected.version
        || expected.minimumVersion !== undefined && task.version < expected.minimumVersion
        || expected.correctionVersion !== undefined
            && task.current_correction_version !== expected.correctionVersion
        || expected.claimFence !== undefined && task.claim_fence !== expected.claimFence) {
        throw new Error("HUMAN_REVIEW_TASK_RESPONSE_BINDING_INVALID");
    }
    if (task.detail_loaded) {
        const expectedClientDigest = task.source_ref?.original_value_client_digest;
        const observedClientDigest = `sha256:${await sha256(new TextEncoder().encode(canonicalStrictJson(task.original_value)).buffer)}`;
        if (observedClientDigest !== expectedClientDigest) {
            throw new Error("HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_INVALID");
        }
    }
    assertReviewRequestCurrent(guard);
    return task;
    },
    commitReviewTask(task) {
      setReviewTasks((current) => [
        task,
        ...current.filter((candidate) => candidate.task_id !== task.task_id),
    ].sort((left, right) => left.confidence - right.confidence || left.task_id.localeCompare(right.task_id)));
    setSelectedReviewTaskId(task.task_id);
    return task;
    },
    ensureReviewProject(guard) {
      if (!safeProject(guard.projectId))
        throw new Error("PROJECT_ID_INVALID");
    const scopeDigest = await sha256(new TextEncoder().encode(`review-bootstrap\u0000${guard.projectId}`).buffer);
    assertReviewRequestCurrent(guard);
    const response = await executeGuardedReviewSkill(guard, "elmos-multimodal-input-orchestrator", "bootstrap_project", {}, `mmi-review-bootstrap-${scopeDigest.slice(0, 40)}`);
    const tenantId = responseString(response, "tenant_id");
    const engineProjectId = responseString(response, "project_id", "engine_project_id");
    if (!boundedOpaque(tenantId) || !boundedOpaque(engineProjectId)) {
        throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_MISSING");
    }
    const prior = reviewEngineScope.current;
    if (prior && (prior.tenantId !== tenantId || prior.projectId !== engineProjectId)) {
        throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_CHANGED");
    }
    assertReviewRequestCurrent(guard);
    reviewEngineScope.current = { tenantId, projectId: engineProjectId };
    },
    refreshReviewQueue() {
      const guard = beginReviewRequest();
    setFeedback("");
    setReviewPropagation(null);
    try {
        await ensureReviewProject(guard);
        const engineScope = reviewEngineScope.current;
        if (!engineScope)
            throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_MISSING");
        const cursorFilterDigest = await sha256(new TextEncoder().encode(canonicalStrictJson({
            tenant_id: engineScope.tenantId,
            project_id: engineScope.projectId,
            kinds: [],
            states: [],
            confidence_lte: 1,
        })).buffer);
        assertReviewRequestCurrent(guard);
        const tasks = [];
        const taskIds = new Set();
        const cursors = new Set();
        let cursor = null;
        let expectedTotal;
        let pageCount = 0;
        do {
            pageCount += 1;
            if (pageCount > maximumReviewQueuePages) {
                throw new Error("HUMAN_REVIEW_TASK_PAGE_LIMIT_EXCEEDED");
            }
            const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "list", {
                kinds: [],
                states: [],
                confidence_lte: 1,
                limit: 200,
                cursor,
            }, `mmi-review-list-${crypto.randomUUID()}`);
            const output = exactReviewOutput(response, ["tasks", "next_cursor", "total"]);
            const rawTasks = output.tasks;
            const total = output.total;
            const nextCursor = output.next_cursor;
            if (!Array.isArray(rawTasks)
                || rawTasks.length > 200
                || typeof total !== "number"
                || !Number.isSafeInteger(total)
                || total < 0
                || total > maximumReviewQueueTasks
                || (nextCursor !== null && (typeof nextCursor !== "string" || !boundedOpaque(nextCursor)))
                || (expectedTotal !== undefined && total !== expectedTotal))
                throw new Error("HUMAN_REVIEW_TASK_LIST_INVALID");
            expectedTotal = total;
            for (const value of rawTasks) {
                const task = reviewTask(value);
                if (!task || taskIds.has(task.task_id)) {
                    throw new Error("HUMAN_REVIEW_TASK_LIST_INVALID");
                }
                taskIds.add(task.task_id);
                tasks.push(task);
            }
            if (tasks.length > total || tasks.length > maximumReviewQueueTasks) {
                throw new Error("HUMAN_REVIEW_TASK_LIST_INVALID");
            }
            if (nextCursor !== null) {
                const lastTask = tasks.at(-1);
                if (cursors.has(nextCursor)
                    || rawTasks.length !== 200
                    || tasks.length >= total
                    || pageCount >= Math.ceil(total / 200)
                    || !lastTask
                    || !exactReviewCursor(nextCursor, cursorFilterDigest, lastTask)) {
                    throw new Error("HUMAN_REVIEW_TASK_CURSOR_INVALID");
                }
                cursors.add(nextCursor);
            }
            cursor = nextCursor;
        } while (cursor !== null);
        if (tasks.length !== expectedTotal) {
            throw new Error("HUMAN_REVIEW_TASK_LIST_CHANGED");
        }
        setReviewTasks(tasks);
        reconcileReviewClaims(tasks);
        setSelectedReviewTaskId("");
        setCorrection("");
        setCorrectionTouched(false);
        setReviewPropagation(null);
        setReviewCurrentCorrection(null);
        setFeedback(`已完整载入 ${tasks.length} 个审阅任务；低置信项优先。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_LIST_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    fetchCurrentReviewCorrection(guard, task) {
      if (task.current_correction_version === 0)
        return undefined;
    const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "current_correction", { task_id: task.task_id }, `mmi-review-current-correction-${task.task_id}-${task.current_correction_version}`);
    const output = exactReviewOutput(response, ["correction"]);
    if (!exactCurrentReviewCorrection(output.correction, task)) {
        throw new Error("HUMAN_REVIEW_CURRENT_CORRECTION_RESPONSE_INVALID");
    }
    assertReviewRequestCurrent(guard);
    return output.correction;
    },
    selectReviewTask(taskId) {
      if (taskId !== selectedReviewTaskId) {
        setCorrection("");
        setCorrectionTouched(false);
        setReviewCurrentCorrection(null);
    }
    setSelectedReviewTaskId(taskId);
    setReviewPropagation(null);
    const summary = reviewTasks.find((task) => task.task_id === taskId);
    if (!summary)
        return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        let detail = summary;
        if (!summary.detail_loaded) {
            const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "get", { task_id: taskId }, `mmi-review-get-${taskId}-${summary.version}`);
            exactReviewOutput(response, ["task"]);
            detail = await validatedReviewTask(response, guard, {
                taskId,
                assetId: summary.asset_id,
                targetKind: summary.target_kind,
                minimumVersion: summary.version,
            });
            assertReviewRequestCurrent(guard);
            const immutableSummary = {
                asset_id: summary.asset_id,
                target_kind: summary.target_kind,
                source_digest: summary.source_digest,
                confidence: summary.confidence,
                reason: summary.reason,
                created_at: summary.created_at,
            };
            const immutableDetail = {
                asset_id: detail.asset_id,
                target_kind: detail.target_kind,
                source_digest: detail.source_digest,
                confidence: detail.confidence,
                reason: detail.reason,
                created_at: detail.created_at,
            };
            if (!detail.detail_loaded
                || canonicalStrictJson(immutableSummary) !== canonicalStrictJson(immutableDetail)
                || detail.version === summary.version
                    && canonicalStrictJson(reviewTaskDynamicState(summary))
                        !== canonicalStrictJson(reviewTaskDynamicState(detail)))
                throw new Error("HUMAN_REVIEW_TASK_DETAIL_INVALID");
        }
        const currentCorrection = await fetchCurrentReviewCorrection(guard, detail);
        assertReviewRequestCurrent(guard);
        commitReviewTask(detail);
        setReviewCurrentCorrection(currentCorrection ?? null);
        setFeedback(currentCorrection
            ? `审阅任务 ${taskId} 的权威原值、来源与当前纠正版本已载入。`
            : `审阅任务 ${taskId} 的权威原值与来源已载入。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setSelectedReviewTaskId("");
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_TASK_DETAIL_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    refreshReviewSources() {
      const asset = assets.find((candidate) => candidate.assetId === correctionTarget);
    if (!asset?.assetId || !asset.sha256 || !positiveInteger(asset.assetVersion)) {
        setFeedback("HUMAN_REVIEW_SOURCE_ASSET_REQUIRED");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        await ensureReviewProject(guard);
        const engineScope = reviewEngineScope.current;
        if (!engineScope)
            throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_MISSING");
        const filterDigest = await sha256(new TextEncoder().encode(canonicalStrictJson({
            schema_version: "human-review-source-filter-v1",
            tenant_id: engineScope.tenantId,
            project_id: engineScope.projectId,
            content_id: asset.assetId,
            content_version: asset.assetVersion,
            kinds: [],
        })).buffer);
        assertReviewRequestCurrent(guard);
        const sources = [];
        const sourceKeys = new Set();
        const cursors = new Set();
        let cursor = null;
        let collectionDigest;
        let collectionGeneration;
        let expectedTotal;
        let pageCount = 0;
        do {
            pageCount += 1;
            if (pageCount > maximumReviewSourcePages) {
                throw new Error("HUMAN_REVIEW_SOURCE_PAGE_LIMIT_EXCEEDED");
            }
            const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "source_list", {
                content_id: asset.assetId,
                expected_asset_version: asset.assetVersion,
                kinds: [],
                limit: 200,
                cursor,
            }, `mmi-review-source-list-${crypto.randomUUID()}`);
            const output = exactReviewOutput(response, ["sources", "next_cursor", "total"]);
            const rawSources = output.sources;
            const total = output.total;
            const nextCursor = output.next_cursor;
            if (!Array.isArray(rawSources)
                || rawSources.length > 200
                || typeof total !== "number"
                || !Number.isSafeInteger(total)
                || total < 0
                || total > maximumReviewSources
                || !(nextCursor === null || typeof nextCursor === "string")
                || expectedTotal !== undefined && total !== expectedTotal)
                throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
            expectedTotal = total;
            for (const value of rawSources) {
                const source = reviewSource(value);
                if (!source
                    || source.detail_loaded
                    || source.content_id !== asset.assetId
                    || source.content_version !== asset.assetVersion
                    || source.source_ref.asset_sha256 !== `sha256:${asset.sha256}`)
                    throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
                const key = reviewSourceKey(source);
                if (sourceKeys.has(key))
                    throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
                sourceKeys.add(key);
                sources.push(source);
            }
            if (sources.length > total || sources.length > maximumReviewSources) {
                throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
            }
            if (nextCursor !== null) {
                const lastSource = sources.at(-1);
                const observedCursorBinding = lastSource
                    ? exactReviewSourceCursor(nextCursor, filterDigest, collectionDigest, collectionGeneration, lastSource)
                    : undefined;
                if (cursors.has(nextCursor)
                    || rawSources.length !== 200
                    || sources.length >= total
                    || pageCount >= Math.ceil(total / 200)
                    || observedCursorBinding === undefined)
                    throw new Error("HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
                collectionDigest = observedCursorBinding.collectionDigest;
                collectionGeneration = observedCursorBinding.collectionGeneration;
                cursors.add(nextCursor);
            }
            cursor = nextCursor;
        } while (cursor !== null);
        if (sources.length !== expectedTotal) {
            throw new Error("HUMAN_REVIEW_SOURCE_COLLECTION_CHANGED");
        }
        assertReviewRequestCurrent(guard);
        setReviewSources([...sources].sort((left, right) => (left.confidence - right.confidence
            || left.target_kind.localeCompare(right.target_kind)
            || left.target_digest.localeCompare(right.target_digest))));
        setSelectedReviewSourceKey("");
        setReviewTargetLocator("");
        setReviewOriginalValue("");
        setFeedback(`已载入 ${sources.length} 个版本绑定的权威待审来源；请选择一项查看原值。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_SOURCE_LIST_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    selectReviewSource(key) {
      setSelectedReviewSourceKey(key);
    setReviewTargetLocator("");
    setReviewOriginalValue("");
    const summary = reviewSources.find((source) => reviewSourceKey(source) === key);
    const asset = assets.find((candidate) => candidate.assetId === correctionTarget);
    if (!summary || !asset?.assetId || !asset.sha256 || !positiveInteger(asset.assetVersion))
        return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "source_get", {
            content_id: summary.content_id,
            expected_asset_version: summary.content_version,
            target_kind: summary.target_kind,
            target_digest: summary.target_digest,
            expected_head_version: summary.head_version,
        }, `mmi-review-source-get-${crypto.randomUUID()}`);
        const output = exactReviewOutput(response, ["source"]);
        const detail = await validatedReviewSource(output.source, {
            contentId: asset.assetId,
            contentVersion: summary.content_version,
            priorSummary: summary,
        });
        assertReviewRequestCurrent(guard);
        if (detail.source_ref.asset_sha256 !== `sha256:${asset.sha256}`) {
            throw new Error("HUMAN_REVIEW_SOURCE_ASSET_DIGEST_INVALID");
        }
        setReviewSources((current) => [
            detail,
            ...current.filter((source) => reviewSourceKey(source) !== key),
        ].sort((left, right) => (left.confidence - right.confidence
            || left.target_kind.localeCompare(right.target_kind)
            || left.target_digest.localeCompare(right.target_digest))));
        setReviewTargetKind(detail.target_kind);
        setReviewTargetLocator(canonicalStrictJson(detail.target));
        setReviewOriginalValue(detail.target_kind === "TEXT" && typeof detail.original_value === "string"
            ? detail.original_value
            : canonicalStrictJson(detail.original_value));
        setReviewConfidence(String(detail.confidence));
        setFeedback("权威来源详情已载入并绑定当前 asset/snapshot/head；现在可创建审阅任务。");
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setSelectedReviewSourceKey("");
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_SOURCE_GET_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    validatedReviewEnqueueReceipt(response, guard, input, outputKeys) {
      exactReviewOutput(response, outputKeys);
    const task = await validatedReviewTask(response, guard, {
        assetId: input.content_id,
        targetKind: input.target_kind,
        state: "QUEUED",
        version: 1,
        correctionVersion: 0,
    });
    assertReviewRequestCurrent(guard);
    const sourceRef = task.source_ref;
    if (!task.detail_loaded
        || !sourceRef
        || task.reason !== input.reason
        || task.source_digest !== input.expected_head_value_digest
        || sourceRef.content_version !== input.expected_asset_version
        || sourceRef.target_digest !== input.target_digest
        || sourceRef.head_version !== input.expected_head_version
        || sourceRef.snapshot_id !== input.expected_snapshot_id
        || sourceRef.snapshot_digest !== input.expected_snapshot_digest
        || sourceRef.head_value_digest !== input.expected_head_value_digest
        || sourceRef.original_value_client_digest !== input.original_value_digest
        || sourceRef.original_value_digest_contract
            !== "sha256:rfc8785-ijson-safeint-v1")
        throw new Error("HUMAN_REVIEW_ENQUEUE_RECEIPT_BINDING_INVALID");
    return task;
    },
    clearReviewEnqueueAttempt(guard, attempt) {
      assertReviewRequestCurrent(guard);
    const attempts = loadReviewEnqueueAttempts(guard.identityScope);
    const persisted = attempts[attempt.request_digest];
    if (!persisted
        || canonicalStrictJson(persisted) !== canonicalStrictJson(attempt))
        throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_BINDING_INVALID");
    delete attempts[attempt.request_digest];
    if (!persistReviewEnqueueAttempts(guard.identityScope, attempts)) {
        throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_CLEAR_FAILED");
    }
    setReviewEnqueueRecoveryCount(Object.values(attempts).filter((candidate) => candidate.project_scope_digest === attempt.project_scope_digest).length);
    setReviewEnqueueRecoveryError("");
    },
    recoverReviewEnqueueAttempts() {
      if (!reviewIdentityScope) {
        setFeedback("HUMAN_REVIEW_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    let recovered = 0;
    let safelyCleared = 0;
    try {
        await ensureReviewProject(guard);
        const projectScopeDigest = await reviewProjectScopeDigest(guard.identityScope, guard.projectId);
        assertReviewRequestCurrent(guard);
        const storedAttempts = loadReviewEnqueueAttempts(guard.identityScope);
        const attempts = Object.values(storedAttempts).filter((attempt) => attempt.project_scope_digest === projectScopeDigest).sort((left, right) => (left.created_at - right.created_at
            || left.request_digest.localeCompare(right.request_digest)));
        if (attempts.length === 0) {
            setReviewEnqueueRecoveryCount(0);
            setReviewEnqueueRecoveryError("");
            setFeedback("当前项目没有待恢复的审阅入队请求。");
            return;
        }
        for (const attempt of attempts) {
            assertReviewRequestCurrent(guard);
            if (attempt.project_scope_digest !== projectScopeDigest) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_BINDING_INVALID");
            }
            const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "enqueue_execute", { recovery_handle: attempt.recovery_handle }, attempt.execute_idempotency_key);
            if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT") {
                const output = exactReviewOutput(response, ["preparation"]);
                if (!exactReviewEnqueuePreparationAbsence(output.preparation, attempt)) {
                    throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
                }
                clearReviewEnqueueAttempt(guard, attempt);
                safelyCleared += 1;
                continue;
            }
            if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED") {
                const output = exactReviewOutput(response, ["preparation"]);
                await validatedReviewEnqueuePreparation(output.preparation, attempt, new Set(["EXPIRED"]));
                assertReviewRequestCurrent(guard);
                clearReviewEnqueueAttempt(guard, attempt);
                safelyCleared += 1;
                continue;
            }
            if (response.code !== "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION") {
                throw new Error("HUMAN_REVIEW_ENQUEUE_EXECUTE_RESPONSE_INVALID");
            }
            const output = exactReviewOutput(response, ["preparation", "task"]);
            const { preparation, input } = await validatedReviewEnqueuePreparation(output.preparation, attempt, new Set(["EXECUTED"]));
            assertReviewRequestCurrent(guard);
            const receiptTask = await validatedReviewEnqueueReceipt(response, guard, input, ["preparation", "task"]);
            if (preparation.task_id !== receiptTask.task_id) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECEIPT_BINDING_INVALID");
            }
            clearReviewEnqueueAttempt(guard, attempt);
            const currentResponse = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "get", { task_id: receiptTask.task_id }, `mmi-review-get-${receiptTask.task_id}-${receiptTask.version}-${crypto.randomUUID()}`);
            exactReviewOutput(currentResponse, ["task"]);
            const currentTask = await validatedReviewTask(currentResponse, guard, {
                priorTask: receiptTask,
                taskId: receiptTask.task_id,
                assetId: input.content_id,
                targetKind: input.target_kind,
                minimumVersion: receiptTask.version,
            });
            commitReviewTask(currentTask);
            recovered += 1;
        }
        setFeedback(`审阅入队恢复完成：${recovered} 个已提交任务载入权威当前状态，${safelyCleared} 个明确未执行或已过期句柄已清理。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            await updateReviewEnqueueRecoveryState(guard.identityScope, guard.projectId);
            setFeedback(error instanceof Error
                ? error.message
                : "HUMAN_REVIEW_ENQUEUE_RECOVERY_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    enqueueReviewTask() {
      const asset = assets.find((candidate) => candidate.assetId === correctionTarget);
    const selectedSource = reviewSources.find((source) => (reviewSourceKey(source) === selectedReviewSourceKey && source.detail_loaded));
    const confidence = selectedSource?.confidence;
    const enqueueReason = reviewReason.trim();
    if (!reviewIdentityScope
        || !asset?.assetId
        || !asset.sha256
        || !positiveInteger(asset.assetVersion)
        || !selectedSource
        || selectedSource.content_id !== asset.assetId
        || selectedSource.content_version !== asset.assetVersion
        || selectedSource.source_ref.asset_sha256 !== `sha256:${asset.sha256}`
        || typeof confidence !== "number"
        || !Number.isFinite(confidence)
        || confidence < 0
        || confidence > 1
        || !exactRequiredText(enqueueReason, 2_000)) {
        setFeedback("HUMAN_REVIEW_ENQUEUE_INPUT_INVALID");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const target = selectedSource.target;
        const originalValue = selectedSource.original_value;
        const sourceRef = selectedSource.source_ref;
        await ensureReviewProject(guard);
        const originalValueClientDigest = `sha256:${await sha256(new TextEncoder().encode(canonicalStrictJson(originalValue)).buffer)}`;
        assertReviewRequestCurrent(guard);
        if (originalValueClientDigest !== selectedSource.original_value_client_digest
            || sourceRef.original_value_client_digest !== originalValueClientDigest)
            throw new Error("HUMAN_REVIEW_SOURCE_VALUE_DIGEST_INVALID");
        const enqueueInput = {
            content_id: asset.assetId,
            expected_asset_version: asset.assetVersion,
            target_kind: selectedSource.target_kind,
            target_digest: selectedSource.target_digest,
            original_value_digest: originalValueClientDigest,
            reason: enqueueReason,
            expected_head_version: selectedSource.head_version,
            expected_snapshot_id: sourceRef.snapshot_id,
            expected_snapshot_digest: sourceRef.snapshot_digest,
            expected_head_value_digest: sourceRef.head_value_digest,
        };
        const enqueueRequestDigest = await reviewEnqueueRequestDigest(enqueueInput);
        const projectScopeDigest = await reviewProjectScopeDigest(guard.identityScope, guard.projectId);
        assertReviewRequestCurrent(guard);
        const storedAttempts = loadReviewEnqueueAttempts(guard.identityScope);
        let enqueueAttempt = storedAttempts[enqueueRequestDigest];
        const recoveringUnknown = enqueueAttempt !== undefined;
        if (!enqueueAttempt) {
            if (Object.values(storedAttempts).some((attempt) => attempt.project_scope_digest === projectScopeDigest)) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_REQUIRED");
            }
            if (Object.keys(storedAttempts).length >= maximumStoredReviewEnqueueAttempts) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_LIMIT_EXCEEDED");
            }
            enqueueAttempt = {
                schema_version: 3,
                identity_scope: guard.identityScope,
                project_scope_digest: projectScopeDigest,
                request_digest: enqueueRequestDigest,
                recovery_handle: `mmi-review-recovery-${crypto.randomUUID()}`,
                prepare_idempotency_key: `mmi-review-enqueue-prepare-${crypto.randomUUID()}`,
                execute_idempotency_key: `mmi-review-enqueue-execute-${crypto.randomUUID()}`,
                created_at: Date.now(),
            };
            if (!persistReviewEnqueueAttempts(guard.identityScope, {
                ...storedAttempts,
                [enqueueRequestDigest]: enqueueAttempt,
            })) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_UNAVAILABLE");
            }
            setReviewEnqueueRecoveryCount(Object.values(storedAttempts).filter((attempt) => attempt.project_scope_digest === projectScopeDigest).length + 1);
            setReviewEnqueueRecoveryError("");
        }
        if (enqueueAttempt.project_scope_digest !== projectScopeDigest
            || enqueueAttempt.request_digest !== enqueueRequestDigest) {
            throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_BINDING_INVALID");
        }
        if (!recoveringUnknown) {
            const preparedResponse = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "enqueue_prepare", {
                recovery_handle: enqueueAttempt.recovery_handle,
                execute_idempotency_key: enqueueAttempt.execute_idempotency_key,
                ...enqueueInput,
            }, enqueueAttempt.prepare_idempotency_key);
            if (preparedResponse.code !== "HUMAN_REVIEW_ENQUEUE_PREPARED") {
                throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARE_RESPONSE_INVALID");
            }
            const preparedOutput = exactReviewOutput(preparedResponse, ["preparation"]);
            const prepared = await validatedReviewEnqueuePreparation(preparedOutput.preparation, enqueueAttempt, new Set(["PREPARED"]));
            assertReviewRequestCurrent(guard);
            if (canonicalStrictJson(prepared.input) !== canonicalStrictJson(enqueueInput)) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_BINDING_INVALID");
            }
        }
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "enqueue_execute", { recovery_handle: enqueueAttempt.recovery_handle }, enqueueAttempt.execute_idempotency_key);
        if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT") {
            const output = exactReviewOutput(response, ["preparation"]);
            if (!exactReviewEnqueuePreparationAbsence(output.preparation, enqueueAttempt)) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
            }
            clearReviewEnqueueAttempt(guard, enqueueAttempt);
            throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT_RETRY_REQUIRED");
        }
        if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED") {
            const output = exactReviewOutput(response, ["preparation"]);
            await validatedReviewEnqueuePreparation(output.preparation, enqueueAttempt, new Set(["EXPIRED"]));
            assertReviewRequestCurrent(guard);
            clearReviewEnqueueAttempt(guard, enqueueAttempt);
            throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED_RETRY_REQUIRED");
        }
        if (response.code !== "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION") {
            throw new Error("HUMAN_REVIEW_ENQUEUE_EXECUTE_RESPONSE_INVALID");
        }
        const output = exactReviewOutput(response, ["preparation", "task"]);
        const executed = await validatedReviewEnqueuePreparation(output.preparation, enqueueAttempt, new Set(["EXECUTED"]));
        assertReviewRequestCurrent(guard);
        if (canonicalStrictJson(executed.input) !== canonicalStrictJson(enqueueInput)) {
            throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_BINDING_INVALID");
        }
        const receiptTask = await validatedReviewEnqueueReceipt(response, guard, executed.input, ["preparation", "task"]);
        if (executed.preparation.task_id !== receiptTask.task_id) {
            throw new Error("HUMAN_REVIEW_ENQUEUE_RECEIPT_BINDING_INVALID");
        }
        clearReviewEnqueueAttempt(guard, enqueueAttempt);
        assertReviewRequestCurrent(guard);
        if (!receiptTask.target
            || canonicalStrictJson(receiptTask.target) !== canonicalStrictJson(target)
            || canonicalStrictJson(receiptTask.original_value) !== canonicalStrictJson(originalValue)
            || receiptTask.confidence !== confidence
            || receiptTask.reason !== enqueueReason
            || receiptTask.source_ref?.content_version !== asset.assetVersion
            || receiptTask.source_ref?.asset_sha256 !== `sha256:${asset.sha256}`
            || receiptTask.source_ref?.original_value_client_digest !== originalValueClientDigest
            || receiptTask.source_ref?.original_value_digest_contract
                !== "sha256:rfc8785-ijson-safeint-v1"
            || receiptTask.source_digest !== sourceRef.head_value_digest
            || canonicalStrictJson(receiptTask.source_ref) !== canonicalStrictJson(sourceRef))
            throw new Error("HUMAN_REVIEW_SOURCE_RESPONSE_BINDING_INVALID");
        const currentResponse = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "get", { task_id: receiptTask.task_id }, `mmi-review-get-${receiptTask.task_id}-${receiptTask.version}`);
        exactReviewOutput(currentResponse, ["task"]);
        const currentTask = await validatedReviewTask(currentResponse, guard, {
            priorTask: receiptTask,
            taskId: receiptTask.task_id,
            assetId: asset.assetId,
            targetKind: selectedSource.target_kind,
            target,
            originalValue,
            bindOriginalValue: true,
            minimumVersion: receiptTask.version,
        });
        assertReviewRequestCurrent(guard);
        commitReviewTask(currentTask);
        setFeedback(recoveringUnknown
            ? `审阅任务 ${currentTask.task_id} 的未知结果已精确恢复；当前权威状态已载入。`
            : `审阅任务 ${currentTask.task_id} 已排队；原始资产保持不变。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            await updateReviewEnqueueRecoveryState(guard.identityScope, guard.projectId);
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_ENQUEUE_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    claimReviewTask() {
      const task = selectedReviewTask();
    if (!task || !reviewIdentityScope) {
        setFeedback("HUMAN_REVIEW_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const storedClaim = reviewClaims[task.task_id];
    const recoverable = storedClaim
        && storedClaim.project_id === projectId
        && validReviewClaim(storedClaim, reviewIdentityScope)
        ? storedClaim
        : undefined;
    if (storedClaim && !recoverable && !discardReviewClaim(task.task_id)) {
        setFeedback("HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED");
        return;
    }
    if (recoverable?.fence !== undefined && validReviewClaim(recoverable, reviewIdentityScope)) {
        setFeedback(`审阅任务 ${task.task_id} 的领取凭证仍有效。`);
        return;
    }
    const attempt = recoverable
        ? recoverable
        : {
            schema_version: 2,
            identity_scope: reviewIdentityScope,
            project_id: projectId,
            task_id: task.task_id,
            token: `review-claim:${crypto.randomUUID()}:${crypto.randomUUID()}`,
            idempotency_key: `mmi-review-claim-${task.task_id}-${crypto.randomUUID()}`,
            expected_version: task.version,
            created_at: Date.now(),
        };
    const guard = beginReviewRequest();
    if (!saveReviewClaim(attempt)) {
        setFeedback("HUMAN_REVIEW_CLAIM_RECOVERY_UNAVAILABLE");
        finishReviewRequest(guard);
        return;
    }
    setFeedback("");
    try {
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "claim", {
            task_id: task.task_id,
            expected_version: attempt.expected_version,
            claim_token: attempt.token,
            lease_seconds: reviewClaimLeaseSeconds,
        }, attempt.idempotency_key);
        exactReviewOutput(response, ["task"]);
        const observedCommittedReplay = recoverable?.fence === undefined
            && task.version === attempt.expected_version + 1
            && ["CLAIMED", "EDITED"].includes(task.state)
            && task.claim_fence !== undefined;
        const claimed = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            state: task.state === "EDITED" ? "EDITED" : "CLAIMED",
            version: attempt.expected_version + 1,
            correctionVersion: task.current_correction_version,
            claimFence: observedCommittedReplay
                ? task.claim_fence
                : (task.claim_fence ?? 0) + 1,
        });
        assertReviewRequestCurrent(guard);
        if (!claimed.claim_fence
            || !claimed.claim_expires_at
            || Date.parse(claimed.claim_expires_at) <= Date.now()
            || claimed.current_correction_digest !== task.current_correction_digest
            || claimed.effective_version !== task.effective_version
            || claimed.effective_digest !== task.effective_digest
            || observedCommittedReplay && claimed.claim_expires_at !== task.claim_expires_at
            || account.status === "authenticated"
                && claimed.claim_actor_id !== account.principal?.actorId) {
            throw new Error("HUMAN_REVIEW_CLAIM_FENCE_MISSING");
        }
        const completedClaim = {
            ...attempt,
            fence: claimed.claim_fence,
            expires_at: claimed.claim_expires_at,
        };
        if (!validReviewClaim(completedClaim, reviewIdentityScope) || !saveReviewClaim(completedClaim)) {
            throw new Error("HUMAN_REVIEW_CLAIM_RECOVERY_UNAVAILABLE");
        }
        assertReviewRequestCurrent(guard);
        commitReviewTask(claimed);
        setFeedback(`审阅任务 ${task.task_id} 已领取；租约写入持久状态。`);
    }
    catch (error) {
        if (!reviewRequestIsCurrent(guard))
            return;
        const failure = failureDetails(error, "HUMAN_REVIEW_CLAIM_FAILED");
        if ([
            "HUMAN_REVIEW_CLAIM_REPLAY_STALE",
            "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
            "HUMAN_REVIEW_TASK_ALREADY_CLAIMED",
            "HUMAN_REVIEW_TASK_NOT_CLAIMABLE",
        ].includes(failure.code)) {
            if (discardReviewClaim(task.task_id)) {
                setReviewTasks((current) => current.filter((candidate) => candidate.task_id !== task.task_id));
                setSelectedReviewTaskId("");
                setFeedback(`${failure.code}；本地领取恢复已清除，请刷新队列后重试。`);
            }
            else {
                setFeedback(`${failure.code}；HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED`);
            }
        }
        else {
            setFeedback(failure.code);
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    correctionValue() {
      if (!correctionTouched)
        throw new Error("HUMAN_REVIEW_CORRECTION_REQUIRED");
    if (selectedReviewTask()?.target_kind === "TEXT")
        return correction;
    try {
        return parseStrictJson(correction);
    }
    catch (error) {
        if (error instanceof StrictJsonError) {
            throw new Error(`HUMAN_REVIEW_CORRECTION_${error.code}`);
        }
        throw error;
    }
    },
    editReviewTask() {
      const task = selectedReviewTask();
    const claim = task ? reviewClaims[task.task_id] : undefined;
    if (!task || !claim || claim.fence === undefined
        || !validReviewClaim(claim, reviewIdentityScope)
        || !exactRequiredText(reviewReason.trim(), 2_000)) {
        setFeedback("HUMAN_REVIEW_TASK_CLAIM_REQUIRED");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const correctedValue = correctionValue();
        const correctionReason = reviewReason.trim();
        const editInput = {
            task_id: task.task_id,
            expected_version: task.version,
            expected_correction_version: task.current_correction_version,
            claim_token: claim.token,
            claim_fence: claim.fence,
            correction: { value: correctedValue, reason: correctionReason },
        };
        const editDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(editInput)).buffer);
        assertReviewRequestCurrent(guard);
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "edit", editInput, `mmi-review-edit-${editDigest}`);
        const editOutput = exactReviewOutput(response, ["correction", "task"]);
        const edited = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            state: "EDITED",
            version: task.version + 1,
            correctionVersion: task.current_correction_version + 1,
            claimFence: claim.fence,
        });
        assertReviewRequestCurrent(guard);
        if (edited.claim_actor_id !== task.claim_actor_id
            || edited.claim_expires_at !== task.claim_expires_at
            || edited.effective_version !== task.effective_version
            || edited.effective_digest !== task.effective_digest
            || !exactReviewCorrection(editOutput.correction, task, edited, correctedValue, correctionReason))
            throw new Error("HUMAN_REVIEW_CORRECTION_RESPONSE_BINDING_INVALID");
        commitReviewTask(edited);
        setReviewCurrentCorrection(editOutput.correction);
        setCorrection("");
        setCorrectionTouched(false);
        setFeedback(`审阅任务 ${edited.task_id} 已创建不可变纠正版本，等待批准或拒绝。`);
    }
    catch (error) {
        if (!reviewRequestIsCurrent(guard))
            return;
        const failure = failureDetails(error, "HUMAN_REVIEW_EDIT_FAILED");
        if ([
            "HUMAN_REVIEW_CLAIM_NOT_OWNED",
            "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
        ].includes(failure.code) && discardReviewClaim(task.task_id)) {
            setReviewTasks((current) => current.filter((candidate) => candidate.task_id !== task.task_id));
            setSelectedReviewTaskId("");
            setFeedback(`${failure.code}；旧身份或任务版本的领取凭证已清除，请刷新队列。`);
        }
        else {
            setFeedback(failure.code);
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    decideReviewTask(operation) {
      const task = selectedReviewTask();
    const claim = task ? reviewClaims[task.task_id] : undefined;
    const visibleCorrection = task && reviewCurrentCorrection
        && exactCurrentReviewCorrection(reviewCurrentCorrection, task)
        ? reviewCurrentCorrection
        : undefined;
    if (!task
        || !claim
        || claim.fence === undefined
        || !validReviewClaim(claim, reviewIdentityScope)
        || !exactRequiredText(reviewReason.trim(), 2_000)
        || operation === "approve" && task.state !== "EDITED"
        || task.current_correction_version > 0 && visibleCorrection === undefined) {
        setFeedback("HUMAN_REVIEW_TASK_CLAIM_REQUIRED");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const authoritativeCorrection = await fetchCurrentReviewCorrection(guard, task);
        assertReviewRequestCurrent(guard);
        if (canonicalStrictJson(authoritativeCorrection ?? null)
            !== canonicalStrictJson(visibleCorrection ?? null)) {
            setReviewCurrentCorrection(authoritativeCorrection ?? null);
            throw new Error("HUMAN_REVIEW_CURRENT_CORRECTION_CHANGED_REVIEW_REQUIRED");
        }
        const decisionReason = reviewReason.trim();
        const decisionInput = {
            task_id: task.task_id,
            expected_version: task.version,
            claim_token: claim.token,
            claim_fence: claim.fence,
            reason: decisionReason,
        };
        const decisionDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(decisionInput)).buffer);
        assertReviewRequestCurrent(guard);
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", operation, decisionInput, `mmi-review-${operation}-${decisionDigest}`);
        const decisionOutput = exactReviewOutput(response, ["decision", "propagations", "task"]);
        const decisionDocument = decisionOutput.decision;
        const propagations = decisionOutput.propagations;
        const decided = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            state: operation === "approve" ? "APPROVED" : "REJECTED",
            version: task.version + 1,
            correctionVersion: task.current_correction_version,
            claimFence: claim.fence,
        });
        assertReviewRequestCurrent(guard);
        const trustedActorId = account.status === "authenticated"
            ? account.principal?.actorId
            : undefined;
        if (!exactReviewDecision(decisionDocument, task, decided, operation, decisionReason, authoritativeCorrection, trustedActorId)
            || decided.current_correction_digest !== task.current_correction_digest
            || decided.effective_version !== task.effective_version
            || decided.effective_digest !== task.effective_digest
            || operation === "approve" && !validReviewPropagations(propagations, task.task_id, {
                exactBatch: true,
                direction: "APPLY",
                decisionId: decisionDocument.decision_id,
                correctionVersion: task.current_correction_version,
                initial: true,
            })
            || operation === "reject" && (!Array.isArray(propagations) || propagations.length !== 0))
            throw new Error("HUMAN_REVIEW_DECISION_RESPONSE_BINDING_INVALID");
        commitReviewTask(decided);
        const discarded = discardReviewClaim(task.task_id);
        setReviewPropagation(operation === "approve" ? response : null);
        const message = operation === "approve"
            ? `审阅任务 ${decided.task_id} 已批准；四个派生传播任务已持久排队。`
            : `审阅任务 ${decided.task_id} 已拒绝；纠正历史仍保留。`;
        setFeedback(discarded ? message : `${message} HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED`);
    }
    catch (error) {
        if (!reviewRequestIsCurrent(guard))
            return;
        const failure = failureDetails(error, `HUMAN_REVIEW_${operation.toUpperCase()}_FAILED`);
        if ([
            "HUMAN_REVIEW_CLAIM_NOT_OWNED",
            "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
        ].includes(failure.code) && discardReviewClaim(task.task_id)) {
            setReviewTasks((current) => current.filter((candidate) => candidate.task_id !== task.task_id));
            setSelectedReviewTaskId("");
            setFeedback(`${failure.code}；旧身份或任务版本的领取凭证已清除，请刷新队列。`);
        }
        else {
            setFeedback(failure.code);
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    transitionClosedReviewTask(operation) {
      const task = selectedReviewTask();
    const visibleCorrection = task && reviewCurrentCorrection
        && exactCurrentReviewCorrection(reviewCurrentCorrection, task)
        ? reviewCurrentCorrection
        : undefined;
    if (!task
        || !exactRequiredText(reviewReason.trim(), 2_000)
        || task.current_correction_version > 0 && visibleCorrection === undefined)
        return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const authoritativeCorrection = await fetchCurrentReviewCorrection(guard, task);
        assertReviewRequestCurrent(guard);
        if (canonicalStrictJson(authoritativeCorrection ?? null)
            !== canonicalStrictJson(visibleCorrection ?? null)) {
            setReviewCurrentCorrection(authoritativeCorrection ?? null);
            throw new Error("HUMAN_REVIEW_CURRENT_CORRECTION_CHANGED_REVIEW_REQUIRED");
        }
        const transitionReason = reviewReason.trim();
        const transitionInput = {
            task_id: task.task_id,
            expected_version: task.version,
            reason: transitionReason,
        };
        const transitionDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(transitionInput)).buffer);
        assertReviewRequestCurrent(guard);
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", operation, transitionInput, `mmi-review-${operation}-${transitionDigest}`);
        const transitionOutput = exactReviewOutput(response, ["decision", "propagations", "task"]);
        const transitionDecision = transitionOutput.decision;
        const transitionPropagations = transitionOutput.propagations;
        const transitioned = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            state: operation === "revert" ? "REVERTING" : "REOPENED",
            version: task.version + 1,
            correctionVersion: task.current_correction_version,
            claimFence: task.claim_fence,
        });
        assertReviewRequestCurrent(guard);
        const trustedActorId = account.status === "authenticated"
            ? account.principal?.actorId
            : undefined;
        if (!exactReviewDecision(transitionDecision, task, transitioned, operation, transitionReason, authoritativeCorrection, trustedActorId)
            || transitioned.current_correction_digest !== task.current_correction_digest
            || transitioned.effective_version !== task.effective_version
            || transitioned.effective_digest !== task.effective_digest
            || operation === "revert" && !validReviewPropagations(transitionPropagations, task.task_id, {
                exactBatch: true,
                direction: "REVERT",
                decisionId: transitionDecision.decision_id,
                correctionVersion: task.current_correction_version,
                initial: true,
            })
            || operation === "reopen" && (!Array.isArray(transitionPropagations) || transitionPropagations.length !== 0))
            throw new Error("HUMAN_REVIEW_DECISION_RESPONSE_BINDING_INVALID");
        commitReviewTask(transitioned);
        const discarded = discardReviewClaim(task.task_id);
        setReviewPropagation(operation === "revert" ? response : null);
        const message = operation === "revert"
            ? `审阅任务 ${transitioned.task_id} 已进入可审计回退传播。`
            : `审阅任务 ${transitioned.task_id} 已重新打开。`;
        setFeedback(discarded ? message : `${message} HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : `HUMAN_REVIEW_${operation.toUpperCase()}_FAILED`);
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    refreshReviewPropagation() {
      const task = selectedReviewTask();
    if (!task)
        return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "propagation_status", { task_id: task.task_id }, `mmi-review-propagation-${task.task_id}-${crypto.randomUUID()}`);
        const statusOutput = exactReviewOutput(response, ["effective", "propagations", "task"]);
        const statusTask = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            minimumVersion: task.version,
        });
        assertReviewRequestCurrent(guard);
        if (!validHistoricalPropagationBatches(statusOutput.propagations, task.task_id)) {
            throw new Error("HUMAN_REVIEW_PROPAGATION_RESPONSE_BINDING_INVALID");
        }
        if (!exactReviewEffective(statusOutput.effective, statusTask, statusOutput.propagations)) {
            throw new Error("HUMAN_REVIEW_EFFECTIVE_RESPONSE_INVALID");
        }
        commitReviewTask(statusTask);
        setReviewPropagation(response);
        setFeedback(`审阅任务 ${task.task_id} 的传播状态已刷新。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_PROPAGATION_STATUS_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
    submitCorrection() {
      const target = assets.find((asset) => asset.assetId === correctionTarget);
    if (!target || !correctionTouched)
        return;
    const currentVersion = target.assetVersion;
    if (!currentVersion) {
        setFeedback("ASSET_VERSION_REQUIRED_FOR_CORRECTION");
        return;
    }
    let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const guard = beginReviewRequest();
    try {
        const correctionInput = {
            content_id: target.assetId,
            expected_version: currentVersion,
            value: correction,
            reason: "USER_REVIEW",
        };
        const correctionDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(correctionInput)).buffer);
        assertReviewRequestCurrent(guard);
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "correct", correctionInput, `mmi-correction-${correctionDigest}`);
        const corrected = outputRecord(response, "correction");
        const persistedAssetStatus = responseString(response, "asset_status");
        const correctedPhase = persistedAssetStatus
            ? phaseFrom({ status: persistedAssetStatus })
            : phaseFrom(response);
        update(target.key, {
            phase: correctedPhase,
            response,
            code: undefined,
            recoveryAttached: !["READY", "QUARANTINED"].includes(correctedPhase),
            assetVersion: positiveInteger(corrected?.version) ?? currentVersion,
        });
        setCorrection("");
        setCorrectionTouched(false);
        if (["READY", "QUARANTINED"].includes(correctedPhase) && target.projectId && target.engineProjectId) {
            try {
                await clearRecovery(target, identityGuard);
                assertReviewRequestCurrent(guard);
            }
            catch {
                if (reviewRequestIsCurrent(guard)) {
                    setFeedback("CORRECTION_APPLIED_RECOVERY_CLEANUP_FAILED");
                }
                return;
            }
        }
        setFeedback("纠错版本已提交；原始资产未被覆盖。");
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : "CORRECTION_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
    },
  },
});
