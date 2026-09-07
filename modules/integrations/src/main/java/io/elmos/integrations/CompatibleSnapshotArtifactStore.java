package io.elmos.integrations;

import io.elmos.snapshot.SnapshotPorts;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Explicit writer selection with verified readers for both snapshot artifact formats.
 *
 * <p>Changing writer mode must not strand snapshots that are already durable. Legacy references
 * ({@code cas:sha256:<hex>}) continue to resolve through the legacy backend, while complete CAS
 * references ({@code cas://sha256/<hex>/<size>}) resolve through the catalogued CAS backend. The
 * reference is validated before dispatch, and each backend remains responsible for verifying the
 * bytes it returns.
 *
 * <p>This is deliberately dual-read rather than an implicit copy-on-read migration. A read cannot
 * mint an ownership binding or a GC root; those state changes require the trusted capture context
 * and the explicit {@link SnapshotPorts.ArtifactStore#retainSnapshot} lifecycle call.
 */
public final class CompatibleSnapshotArtifactStore
        implements SnapshotPorts.ArtifactStore, SnapshotPorts.ArtifactReader {

    public enum WriterMode {
        LEGACY,
        CAS
    }

    private static final String LEGACY_PREFIX = "cas:sha256:";
    private static final String LEGACY_PARTICIPANT = "compatible.legacy-participant";
    private static final String CAS_PARTICIPANT = "compatible.cas-participant";

    private final WriterMode writerMode;
    private final SnapshotPorts.ArtifactStore legacyWriter;
    private final SnapshotPorts.ArtifactReader legacyReader;
    private final SnapshotPorts.ArtifactStore casWriter;
    private final SnapshotPorts.ArtifactReader casReader;

    public CompatibleSnapshotArtifactStore(
            WriterMode writerMode,
            SnapshotPorts.ArtifactStore legacyWriter,
            SnapshotPorts.ArtifactReader legacyReader,
            SnapshotPorts.ArtifactStore casWriter,
            SnapshotPorts.ArtifactReader casReader
    ) {
        this.writerMode = Objects.requireNonNull(writerMode, "writerMode");
        this.legacyWriter = Objects.requireNonNull(legacyWriter, "legacyWriter");
        this.legacyReader = Objects.requireNonNull(legacyReader, "legacyReader");
        this.casWriter = Objects.requireNonNull(casWriter, "casWriter");
        this.casReader = Objects.requireNonNull(casReader, "casReader");
    }

    public WriterMode writerMode() {
        return writerMode;
    }

    @Override
    public String putIfAbsent(SnapshotPorts.ArtifactResourceContext resource,
                              String sha256,
                              long size,
                              InputStream content,
                              String mediaType) {
        return writer().putIfAbsent(resource, sha256, size, content, mediaType);
    }

    @Override
    public InputStream open(SnapshotPorts.ArtifactResourceContext resource, String reference) {
        Objects.requireNonNull(resource, "resource");
        if (isLegacy(reference)) {
            return legacyReader.open(resource, reference);
        }
        if (reference != null && reference.startsWith(CasBackedArtifactStore.SCHEME)) {
            // Parse before dispatch so a backend can never accidentally treat a partial URI as a
            // path or perform an authorization lookup for a malformed identity.
            CasBackedArtifactStore.parse(reference);
            return casReader.open(resource, reference);
        }
        throw new IllegalArgumentException("unsupported snapshot artifact reference");
    }

    @Override
    public void retainSnapshot(SnapshotPorts.ArtifactResourceContext resource,
                               String snapshotId,
                               List<String> references) {
        retainSnapshotGeneration(resource, snapshotId, references);
    }

    @Override
    public SnapshotPorts.ArtifactRetention retainSnapshotGeneration(
            SnapshotPorts.ArtifactResourceContext resource,
            String snapshotId,
            List<String> references
    ) {
        Objects.requireNonNull(resource, "resource");
        requireSnapshotId(snapshotId);
        Objects.requireNonNull(references, "references");
        if (references.isEmpty()) {
            throw new IllegalArgumentException("snapshot references must not be empty");
        }

        List<String> legacy = new ArrayList<>();
        List<String> cas = new ArrayList<>();
        for (String reference : List.copyOf(references)) {
            if (isLegacy(reference)) {
                legacy.add(reference);
            } else if (reference != null && reference.startsWith(CasBackedArtifactStore.SCHEME)) {
                CasBackedArtifactStore.parse(reference);
                cas.add(reference);
            } else {
                throw new IllegalArgumentException("unsupported snapshot artifact reference");
            }
        }

        SnapshotPorts.ArtifactRetention retention =
                SnapshotPorts.ArtifactRetention.untracked(snapshotId);
        SnapshotPorts.ArtifactRetention legacyRetention = null;
        if (!legacy.isEmpty()) {
            legacyRetention = legacyWriter.retainSnapshotGeneration(
                    resource, snapshotId, legacy);
            retention = retention.merge(legacyRetention).merge(
                    new SnapshotPorts.ArtifactRetention(
                            snapshotId, java.util.Map.of(LEGACY_PARTICIPANT, 1L)));
        }
        try {
            if (!cas.isEmpty()) {
                retention = retention.merge(casWriter.retainSnapshotGeneration(
                        resource, snapshotId, cas)).merge(
                        new SnapshotPorts.ArtifactRetention(
                                snapshotId, java.util.Map.of(CAS_PARTICIPANT, 1L)));
            }
        } catch (RuntimeException failure) {
            // Each backend owns all-or-none compensation for its own batch. In particular, never
            // call CAS release here: a rejected retry may refer to a pre-existing live logical
            // root, and releasing it would turn a harmless conflict into data loss. The current
            // legacy backend has no GC lifecycle; this call only compensates a future backend
            // that successfully created state before the CAS backend failed.
            if (legacyRetention != null) {
                compensateLegacyRelease(resource, legacyRetention, failure);
            }
            throw failure;
        }
        return retention;
    }

    @Override
    @Deprecated(forRemoval = false)
    public void releaseSnapshot(SnapshotPorts.ArtifactResourceContext resource, String snapshotId) {
        Objects.requireNonNull(resource, "resource");
        requireSnapshotId(snapshotId);
        throw new UnsupportedOperationException(
                "compatible snapshot release requires the participant generation token");
    }

    @Override
    public void releaseSnapshotGeneration(
            SnapshotPorts.ArtifactResourceContext resource,
            SnapshotPorts.ArtifactRetention retention
    ) {
        Objects.requireNonNull(resource, "resource");
        Objects.requireNonNull(retention, "retention");
        requireSnapshotId(retention.snapshotId());
        boolean casParticipant = retention.generations().containsKey(CAS_PARTICIPANT);
        boolean legacyParticipant = retention.generations().containsKey(LEGACY_PARTICIPANT);
        if (!casParticipant && !legacyParticipant) {
            throw new IllegalArgumentException(
                    "compatible retention does not identify a participating backend");
        }
        RuntimeException failure = null;
        if (casParticipant) {
            try {
                casWriter.releaseSnapshotGeneration(resource, retention);
            } catch (RuntimeException error) {
                failure = error;
            }
        }
        if (legacyParticipant) {
            try {
                legacyWriter.releaseSnapshotGeneration(resource, retention);
            } catch (RuntimeException error) {
                if (failure == null) failure = error;
                else failure.addSuppressed(error);
            }
        }
        if (failure != null) throw failure;
    }

    private SnapshotPorts.ArtifactStore writer() {
        return writerMode == WriterMode.CAS ? casWriter : legacyWriter;
    }

    private void compensateLegacyRelease(SnapshotPorts.ArtifactResourceContext resource,
                                         SnapshotPorts.ArtifactRetention retention,
                                         RuntimeException failure) {
        try {
            legacyWriter.releaseSnapshotGeneration(resource, retention);
        } catch (RuntimeException cleanupFailure) {
            failure.addSuppressed(cleanupFailure);
        }
    }

    private static boolean isLegacy(String reference) {
        return reference != null
                && reference.matches(LEGACY_PREFIX + "[0-9a-f]{64}");
    }

    private static void requireSnapshotId(String snapshotId) {
        // ArtifactRetention is the persistence contract passed between capture, reconciliation,
        // and release. Reuse its canonical boundary before dispatching to any backend so an ID can
        // never produce lifecycle state that cannot be represented by the returned token.
        SnapshotPorts.ArtifactRetention.untracked(snapshotId);
    }
}
