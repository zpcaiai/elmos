package io.elmos.workspaceservice;

import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.command.CreateContainerCmd;
import com.github.dockerjava.api.exception.NotFoundException;
import com.github.dockerjava.api.model.AccessMode;
import com.github.dockerjava.api.model.Bind;
import com.github.dockerjava.api.model.Capability;
import com.github.dockerjava.api.model.HostConfig;
import com.github.dockerjava.api.model.Volume;
import com.github.luben.zstd.ZstdInputStream;
import io.elmos.workspace.WorkspaceInfrastructurePorts;
import io.elmos.workspace.WorkspaceModels;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream;
import org.apache.commons.compress.archivers.zip.ZipEncoding;
import org.apache.commons.compress.archivers.zip.ZipEncodingHelper;

import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/** Materializes an already-authorized, read-verified snapshot archive into Docker volumes. */
final class DockerSnapshotVolumeMaterializer
        implements WorkspaceInfrastructurePorts.SnapshotVolumeMaterializer {

    // The helper has no workload of its own; it must remain alive while docker-java streams an
    // authorized archive. Sixty seconds was shorter than a valid 1 GiB copy on a constrained
    // 0.25-CPU helper. The provisioning request itself owns the bounded operation lifecycle and
    // finally removes this container; this value is only a fail-safe upper lifetime.
    static final String MATERIALIZER_IDLE_SECONDS = "43200";
    static final String MATERIALIZER_ENTRYPOINT = "/bin/sleep";
    static final int MAX_ARCHIVE_ENTRIES = 100_000;
    static final long MAX_EXPANDED_SOURCE_BYTES = 256L * 1024 * 1024;
    static final long MAX_TAR_METADATA_BYTES = 64L * 1024 * 1024;
    static final long MAX_TAR_ENTRY_HEADER_BYTES = 64L * 1024;
    static final int MAX_ARCHIVE_PATH_BYTES = 4096;
    private static final int TAR_RECORD_BYTES = 512;
    private static final ZipEncoding TAR_UTF8_ENCODING =
            ZipEncodingHelper.getZipEncoding(StandardCharsets.UTF_8);
    private static final long ZSTD_CONTAINER_OVERHEAD_BYTES = 1024L * 1024;
    private static final Set<PosixFilePermission> PRIVATE_DIRECTORY_PERMISSIONS = Set.of(
            PosixFilePermission.OWNER_READ,
            PosixFilePermission.OWNER_WRITE,
            PosixFilePermission.OWNER_EXECUTE);
    private static final Set<PosixFilePermission> PRIVATE_SPOOL_WRITE_PERMISSIONS = Set.of(
            PosixFilePermission.OWNER_READ,
            PosixFilePermission.OWNER_WRITE);
    private static final Set<PosixFilePermission> PRIVATE_SPOOL_READ_PERMISSIONS = Set.of(
            PosixFilePermission.OWNER_READ);

    private final DockerClient docker;
    private final WorkspaceInfrastructurePorts.SnapshotArtifactResolver snapshots;
    private final WorkspaceInfrastructurePorts.SnapshotArtifactReader artifacts;
    private final String helperImageDigest;
    private final WorkspaceInfrastructurePorts.ApprovedImageRegistry images;

    DockerSnapshotVolumeMaterializer(
            DockerClient docker,
            WorkspaceInfrastructurePorts.SnapshotArtifactResolver snapshots,
            WorkspaceInfrastructurePorts.SnapshotArtifactReader artifacts,
            String helperImageDigest,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images
    ) {
        this.docker = Objects.requireNonNull(docker, "docker");
        this.snapshots = Objects.requireNonNull(snapshots, "snapshots");
        this.artifacts = Objects.requireNonNull(artifacts, "artifacts");
        this.helperImageDigest = Objects.requireNonNull(
                helperImageDigest, "helperImageDigest");
        this.images = Objects.requireNonNull(images, "images");
        if (!helperImageDigest.matches("sha256:[0-9a-f]{64}")) {
            throw new IllegalArgumentException("snapshot helper image digest is required");
        }
    }

    @Override
    public void materialize(
            WorkspaceModels.WorkspaceRequest request,
            String snapshotVolume,
            String workspaceVolume
    ) {
        WorkspaceInfrastructurePorts.SnapshotArtifact archive =
                requireBoundArtifact(request, snapshots.resolve(request));
        long expandedLimit = expandedSourceLimit(request);
        long decompressedLimit = maximumDecompressedArchiveBytes(expandedLimit);
        long compressedLimit = Math.addExact(
                decompressedLimit, ZSTD_CONTAINER_OVERHEAD_BYTES);
        try (SnapshotSpool spool = spoolArchive(artifacts, archive, compressedLimit)) {
            ArchiveInventory inventory = preflightArchive(
                    spool, archive, expandedLimit);
            images.requireApproved("snapshot-materializer", helperImageDigest);
            HostConfig host = HostConfig.newHostConfig()
                    .withPrivileged(false)
                    .withReadonlyRootfs(true)
                    .withCapDrop(Capability.ALL)
                    .withSecurityOpts(List.of("no-new-privileges:true"))
                    .withNetworkMode("none")
                    .withMemory(256L * 1024 * 1024)
                    .withMemorySwap(256L * 1024 * 1024)
                    .withNanoCPUs(250_000_000L)
                    .withPidsLimit(64L)
                    .withTmpFs(Map.of("/tmp", "rw,noexec,nosuid,size=64m"))
                    .withBinds(
                            new Bind(snapshotVolume, new Volume("/snapshot"), AccessMode.rw),
                            new Bind(workspaceVolume, new Volume("/workspace"), AccessMode.rw));
            String helper = configureHelperProcess(
                    docker.createContainerCmd(helperImageDigest))
                    .withName("elmos-materialize-" + UUID.randomUUID())
                    .withUser("10001:10001")
                    .withHostConfig(host)
                    .withLabels(helperLabels(request, archive))
                    .exec()
                    .getId();
            try {
                docker.startContainerCmd(helper).exec();
                copy(helper, "/snapshot", spool, decompressedLimit,
                        inventory.archiveBytes());
                copy(helper, "/workspace", spool, decompressedLimit,
                        inventory.archiveBytes());
            } finally {
                try {
                    docker.removeContainerCmd(helper).withForce(true).exec();
                } catch (NotFoundException ignored) {
                    // The helper may already have been reaped; it owns no durable state.
                }
            }
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("snapshot materialization failed", error);
        }
    }

    /** Overrides image-owned ENTRYPOINT/CMD so an approved helper cannot run hidden startup code. */
    static CreateContainerCmd configureHelperProcess(CreateContainerCmd command) {
        return Objects.requireNonNull(command, "command")
                .withEntrypoint(MATERIALIZER_ENTRYPOINT)
                .withCmd(MATERIALIZER_IDLE_SECONDS);
    }

    private static long expandedSourceLimit(WorkspaceModels.WorkspaceRequest request) {
        long workspaceBytes = Math.multiplyExact(
                request.resources().diskMb(), 1024L * 1024L);
        // The same source is copied to two volumes, so each copy receives half the disk budget.
        return Math.min(MAX_EXPANDED_SOURCE_BYTES, workspaceBytes / 2L);
    }

    private static long maximumDecompressedArchiveBytes(long maximumExpandedBytes) {
        return Math.addExact(maximumExpandedBytes, MAX_TAR_METADATA_BYTES);
    }

    private ArchiveInventory preflightArchive(
            SnapshotSpool spool,
            WorkspaceInfrastructurePorts.SnapshotArtifact archive,
            long expandedLimit
    ) {
        try (InputStream source = spool.open()) {
            return inspectArchive(
                    source, archive.sha256(), archive.sizeBytes(), expandedLimit);
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("snapshot archive preflight failed", error);
        }
    }

    static ArchiveInventory inspectArchive(
            InputStream source,
            String expectedSha256,
            long expectedCompressedSize,
            long maximumExpandedBytes
    ) throws IOException {
        if (maximumExpandedBytes < 1 || maximumExpandedBytes > MAX_EXPANDED_SOURCE_BYTES) {
            throw new IllegalArgumentException("expanded archive limit is outside policy");
        }
        Set<String> paths = new HashSet<>();
        Set<String> symlinkPaths = new HashSet<>();
        Set<String> descendantParentPaths = new HashSet<>();
        int entries = 0;
        long expandedBytes = 0;
        try (VerifyingArchiveInputStream verified = new VerifyingArchiveInputStream(
                     source, expectedSha256, expectedCompressedSize);
             ZstdInputStream zstd = new ZstdInputStream(verified);
             BoundedExpandedInputStream expanded = new BoundedExpandedInputStream(
                     zstd, maximumDecompressedArchiveBytes(maximumExpandedBytes));
             CanonicalTarArchiveInputStream tar = new CanonicalTarArchiveInputStream(
                     expanded, StandardCharsets.UTF_8.name())) {
            byte[] buffer = new byte[64 * 1024];
            TarArchiveEntry entry;
            while (true) {
                long beforeHeader = expanded.observedBytes();
                entry = tar.getNextEntry();
                long headerBytes = expanded.observedBytes() - beforeHeader;
                if (headerBytes > MAX_TAR_ENTRY_HEADER_BYTES) {
                    throw new SecurityException(
                            "snapshot archive per-entry metadata limit exceeded");
                }
                enforceMetadataBudget(expanded.observedBytes(), expandedBytes);
                if (entry == null) {
                    tar.requireNoPendingCanonicalEntry();
                    break;
                }
                tar.requireCanonicalProducerEncoding(entry);
                entries = Math.addExact(entries, 1);
                if (entries > MAX_ARCHIVE_ENTRIES) {
                    throw new SecurityException("snapshot archive entry limit exceeded");
                }
                String path = validateArchivePath(entry.getName());
                if (!paths.add(path)) {
                    throw new SecurityException("snapshot archive contains duplicate paths");
                }
                rejectDangerousExtendedMetadata(entry);
                if (!entry.isCheckSumOK() || entry.isSparse()
                        || entry.isPaxHeader() || entry.isGlobalPaxHeader()) {
                    throw new SecurityException(
                            "snapshot archive contains unsupported encoded metadata");
                }
                boolean symbolicLink = entry.isSymbolicLink();
                if (!tar.canReadEntryData(entry)
                        || entry.isLink()
                        || entry.isCharacterDevice()
                        || entry.isBlockDevice()
                        || entry.isFIFO()
                        || (!entry.isFile() && !entry.isDirectory() && !symbolicLink)) {
                    throw new SecurityException("snapshot archive contains an unsafe entry type");
                }
                if ((entry.getMode() & 07000) != 0) {
                    throw new SecurityException("snapshot archive contains privileged mode bits");
                }
                if (entry.getLongUserId() != 10001L || entry.getLongGroupId() != 10001L) {
                    throw new SecurityException(
                            "snapshot archive ownership does not match the canonical producer");
                }
                rejectSymlinkAncestor(path, symlinkPaths);
                if (symbolicLink) {
                    validateArchiveSymlink(path, entry.getLinkName());
                    if (descendantParentPaths.contains(path)) {
                        throw new SecurityException(
                                "snapshot archive symlink replaces an existing path parent");
                    }
                    symlinkPaths.add(path);
                }
                recordParentPaths(path, descendantParentPaths);
                long declared = entry.getSize();
                if (declared < 0
                        || ((entry.isDirectory() || symbolicLink) && declared != 0)) {
                    throw new SecurityException("snapshot archive entry size is invalid");
                }
                if (declared > maximumExpandedBytes
                        || expandedBytes > maximumExpandedBytes - declared) {
                    throw new SecurityException("snapshot archive expanded size exceeds policy");
                }
                long observed = 0;
                int read;
                while ((read = tar.read(buffer)) >= 0) {
                    observed = Math.addExact(observed, read);
                    if (observed > declared) {
                        throw new SecurityException(
                                "snapshot archive entry exceeds its declared size");
                    }
                }
                if (observed != declared) {
                    throw new SecurityException(
                            "snapshot archive entry is shorter than its declared size");
                }
                expandedBytes = Math.addExact(expandedBytes, observed);
            }
            int trailing;
            while ((trailing = expanded.read(buffer)) >= 0) {
                for (int index = 0; index < trailing; index++) {
                    if (buffer[index] != 0) {
                        throw new SecurityException(
                                "snapshot archive contains trailing non-zero data");
                    }
                }
            }
            enforceMetadataBudget(expanded.observedBytes(), expandedBytes);
            verified.requireComplete();
            return new ArchiveInventory(entries, expandedBytes, expanded.observedBytes());
        }
    }

    private static void enforceMetadataBudget(long decompressedBytes, long expandedBytes) {
        long metadataBytes = decompressedBytes - expandedBytes;
        if (metadataBytes < 0 || metadataBytes > MAX_TAR_METADATA_BYTES) {
            throw new SecurityException("snapshot archive metadata limit exceeded");
        }
    }

    private static void rejectDangerousExtendedMetadata(TarArchiveEntry entry) {
        for (String name : entry.getExtraPaxHeaders().keySet()) {
            String normalized = name.toLowerCase(java.util.Locale.ROOT);
            if (!normalized.equals("path") && !normalized.equals("linkpath")) {
                throw new SecurityException(
                        "snapshot archive contains non-canonical PAX metadata");
            }
        }
    }

    /**
     * Commons Compress intentionally hides PAX and GNU pseudo entries from callers.  That is
     * convenient for general extraction, but it is not sufficient at this trust boundary: an
     * effective entry can look safe after a non-canonical extension changed its metadata.  This
     * reader observes the raw records before the parser consumes them and accepts only the exact
     * POSIX path/linkpath extension emitted by {@code DeterministicSnapshotArchiver}.
     */
    static final class CanonicalTarArchiveInputStream extends TarArchiveInputStream {
        private ByteArrayOutputStream currentPaxPayload;
        private byte[] currentPaxHeader;
        private long currentPaxSize;
        private PaxExtension pendingPax;
        private byte[] pendingEntryHeader;

        CanonicalTarArchiveInputStream(InputStream input, String encoding) {
            super(input, encoding);
        }

        @Override
        protected byte[] readRecord() throws IOException {
            finishPaxPayload();
            byte[] record = super.readRecord();
            if (record == null || isZeroRecord(record)) {
                return record;
            }
            byte typeFlag = record[TarArchiveEntry.LF_OFFSET];
            if (typeFlag == TarArchiveEntry.LF_GNUTYPE_LONGNAME
                    || typeFlag == TarArchiveEntry.LF_GNUTYPE_LONGLINK
                    || typeFlag == TarArchiveEntry.LF_PAX_GLOBAL_EXTENDED_HEADER
                    || typeFlag == TarArchiveEntry.LF_PAX_EXTENDED_HEADER_UC) {
                throw new SecurityException(
                        "snapshot archive contains a non-canonical tar extension");
            }
            if (typeFlag == TarArchiveEntry.LF_PAX_EXTENDED_HEADER_LC) {
                if (pendingPax != null || currentPaxPayload != null) {
                    throw new SecurityException(
                            "snapshot archive contains stacked PAX metadata");
                }
                TarArchiveEntry paxHeader = new TarArchiveEntry(
                        record, TAR_UTF8_ENCODING, false);
                if (!paxHeader.isCheckSumOK() || paxHeader.getSize() < 1
                        || paxHeader.getSize() > MAX_TAR_ENTRY_HEADER_BYTES) {
                    throw new SecurityException(
                            "snapshot archive per-entry metadata limit exceeded");
                }
                currentPaxHeader = record.clone();
                currentPaxSize = paxHeader.getSize();
                currentPaxPayload = new ByteArrayOutputStream(
                        Math.toIntExact(currentPaxSize));
            } else {
                if (pendingEntryHeader != null) {
                    throw new SecurityException(
                            "snapshot archive parser state is not canonical");
                }
                pendingEntryHeader = record.clone();
            }
            return record;
        }

        @Override
        public int read(byte[] bytes, int offset, int length) throws IOException {
            int read = super.read(bytes, offset, length);
            if (read > 0 && currentPaxPayload != null) {
                currentPaxPayload.write(bytes, offset, read);
                if (currentPaxPayload.size() > currentPaxSize) {
                    throw new SecurityException(
                            "snapshot archive PAX metadata exceeds its declared size");
                }
            }
            return read;
        }

        void requireCanonicalProducerEncoding(TarArchiveEntry entry) {
            Objects.requireNonNull(entry, "entry");
            byte[] rawHeader = pendingEntryHeader;
            if (rawHeader == null) {
                throw new SecurityException("snapshot archive entry header is missing");
            }
            pendingEntryHeader = null;

            requireCanonicalProducerMetadata(entry);
            boolean needsPathPax = requiresPax(entry.getName());
            boolean needsLinkPax = entry.isSymbolicLink()
                    && requiresPax(entry.getLinkName());
            PaxExtension pax = pendingPax;
            pendingPax = null;
            if (pax == null) {
                if (needsPathPax || needsLinkPax) {
                    throw new SecurityException(
                            "snapshot archive omits the canonical POSIX path extension");
                }
            } else {
                requireCanonicalPax(pax, entry, needsPathPax, needsLinkPax);
            }

            TarArchiveEntry canonical = canonicalEntry(entry);
            byte[] expectedHeader = new byte[TAR_RECORD_BYTES];
            try {
                canonical.writeEntryHeader(expectedHeader, TAR_UTF8_ENCODING, false);
            } catch (IOException encodingFailure) {
                throw new SecurityException(
                        "snapshot archive canonical header cannot be encoded", encodingFailure);
            }
            if (!Arrays.equals(rawHeader, expectedHeader)) {
                throw new SecurityException(
                        "snapshot archive entry header is not canonical");
            }
        }

        void requireNoPendingCanonicalEntry() {
            finishPaxPayload();
            if (pendingEntryHeader != null || pendingPax != null
                    || currentPaxPayload != null) {
                throw new SecurityException(
                        "snapshot archive ended with incomplete canonical metadata");
            }
        }

        private void finishPaxPayload() {
            if (currentPaxPayload == null) {
                return;
            }
            byte[] payload = currentPaxPayload.toByteArray();
            if (payload.length != currentPaxSize || pendingPax != null) {
                throw new SecurityException(
                        "snapshot archive PAX metadata size is not canonical");
            }
            pendingPax = new PaxExtension(
                    currentPaxHeader, payload, parseCanonicalPax(payload));
            currentPaxPayload = null;
            currentPaxHeader = null;
            currentPaxSize = 0;
        }

        private static void requireCanonicalPax(
                PaxExtension pax,
                TarArchiveEntry entry,
                boolean needsPathPax,
                boolean needsLinkPax
        ) {
            Map<String, String> values = pax.values();
            if (values.containsKey("path") != needsPathPax
                    || values.containsKey("linkpath") != needsLinkPax
                    || (needsPathPax && !entry.getName().equals(values.get("path")))
                    || (needsLinkPax && !entry.getLinkName().equals(values.get("linkpath")))) {
                throw new SecurityException(
                        "snapshot archive PAX metadata is not producer-canonical");
            }
            String expectedName = canonicalPaxHeaderName(entry.getName());
            TarArchiveEntry expected = new TarArchiveEntry(
                    expectedName, TarArchiveEntry.LF_PAX_EXTENDED_HEADER_LC);
            expected.setSize(pax.payload().length);
            expected.setModTime(0);
            byte[] expectedHeader = new byte[TAR_RECORD_BYTES];
            try {
                expected.writeEntryHeader(expectedHeader, TAR_UTF8_ENCODING, false);
            } catch (IOException encodingFailure) {
                throw new SecurityException(
                        "snapshot archive canonical PAX header cannot be encoded",
                        encodingFailure);
            }
            if (!Arrays.equals(pax.header(), expectedHeader)) {
                throw new SecurityException(
                        "snapshot archive PAX header is not producer-canonical");
            }
        }

        private static TarArchiveEntry canonicalEntry(TarArchiveEntry entry) {
            TarArchiveEntry canonical = new TarArchiveEntry(
                    entry.getName(), entry.getLinkFlag());
            canonical.setLinkName(entry.getLinkName());
            canonical.setSize(entry.getSize());
            canonical.setMode(entry.getMode());
            canonical.setUserId(10001);
            canonical.setGroupId(10001);
            canonical.setUserName("elmos");
            canonical.setGroupName("elmos");
            canonical.setModTime(0);
            return canonical;
        }

        private static void requireCanonicalProducerMetadata(TarArchiveEntry entry) {
            int expectedMode;
            byte expectedType;
            if (entry.isSymbolicLink()) {
                expectedMode = 0777;
                expectedType = TarArchiveEntry.LF_SYMLINK;
            } else if (entry.isDirectory()) {
                expectedMode = 0755;
                expectedType = TarArchiveEntry.LF_DIR;
            } else if (entry.isFile()) {
                if (entry.getMode() != 0644 && entry.getMode() != 0755) {
                    throw new SecurityException(
                            "snapshot archive file mode is not producer-canonical");
                }
                expectedMode = entry.getMode();
                expectedType = TarArchiveEntry.LF_NORMAL;
            } else {
                throw new SecurityException(
                        "snapshot archive entry type is not producer-canonical");
            }
            if (entry.getLinkFlag() != expectedType || entry.getMode() != expectedMode
                    || entry.getLongUserId() != 10001L
                    || entry.getLongGroupId() != 10001L
                    || !"elmos".equals(entry.getUserName())
                    || !"elmos".equals(entry.getGroupName())
                    || entry.getLastModifiedTime() == null
                    || entry.getLastModifiedTime().toMillis() != 0L
                    || entry.getLastAccessTime() != null
                    || entry.getStatusChangeTime() != null
                    || entry.getCreationTime() != null
                    || ((!entry.isSymbolicLink()) && !entry.getLinkName().isEmpty())) {
                throw new SecurityException(
                        "snapshot archive metadata does not match the canonical producer");
            }
        }

        private static Map<String, String> parseCanonicalPax(byte[] payload) {
            Map<String, String> values = new LinkedHashMap<>();
            int offset = 0;
            while (offset < payload.length) {
                int space = offset;
                while (space < payload.length && payload[space] != ' ') {
                    byte value = payload[space];
                    if (value < '0' || value > '9') {
                        throw new SecurityException(
                                "snapshot archive PAX length is invalid");
                    }
                    space++;
                }
                if (space == offset || space >= payload.length
                        || payload[offset] == '0') {
                    throw new SecurityException(
                            "snapshot archive PAX length is not canonical");
                }
                int recordLength;
                try {
                    recordLength = Integer.parseInt(new String(
                            payload, offset, space - offset, StandardCharsets.US_ASCII));
                } catch (NumberFormatException invalidLength) {
                    throw new SecurityException(
                            "snapshot archive PAX length is invalid", invalidLength);
                }
                if (recordLength <= space - offset + 3
                        || recordLength > payload.length - offset) {
                    throw new SecurityException(
                            "snapshot archive PAX record exceeds its payload");
                }
                int recordEnd = offset + recordLength;
                if (payload[recordEnd - 1] != '\n') {
                    throw new SecurityException(
                            "snapshot archive PAX record is not newline terminated");
                }
                int equals = space + 1;
                while (equals < recordEnd - 1 && payload[equals] != '=') {
                    equals++;
                }
                if (equals == space + 1 || equals >= recordEnd - 1) {
                    throw new SecurityException(
                            "snapshot archive PAX record is malformed");
                }
                String key = new String(
                        payload, space + 1, equals - space - 1,
                        StandardCharsets.US_ASCII);
                if ((!key.equals("path") && !key.equals("linkpath"))
                        || values.containsKey(key)) {
                    throw new SecurityException(
                            "snapshot archive contains non-canonical PAX metadata");
                }
                byte[] rawValue = Arrays.copyOfRange(payload, equals + 1, recordEnd - 1);
                String value = new String(rawValue, StandardCharsets.UTF_8);
                if (!Arrays.equals(rawValue, value.getBytes(StandardCharsets.UTF_8))
                        || !requiresPax(value)) {
                    throw new SecurityException(
                            "snapshot archive PAX path value is not canonical UTF-8");
                }
                values.put(key, value);
                offset = recordEnd;
            }
            if (values.isEmpty()) {
                throw new SecurityException("snapshot archive PAX metadata is empty");
            }
            return Map.copyOf(values);
        }

        private static boolean requiresPax(String value) {
            return utf8Length(value) >= TarArchiveEntry.NAMELEN
                    || value.codePoints().anyMatch(codePoint -> codePoint > 0x7f);
        }

        private static String canonicalPaxHeaderName(String entryName) {
            StringBuilder stripped = new StringBuilder(entryName.length());
            for (int index = 0; index < entryName.length(); index++) {
                char value = (char) (entryName.charAt(index) & 0x7f);
                stripped.append(value == 0 || value == '/' || value == '\\' ? '_' : value);
            }
            String name = "./PaxHeaders.X/" + stripped;
            return name.length() >= TarArchiveEntry.NAMELEN
                    ? name.substring(0, TarArchiveEntry.NAMELEN - 1)
                    : name;
        }

        private static int utf8Length(String value) {
            return value == null ? 0 : value.getBytes(StandardCharsets.UTF_8).length;
        }

        private static boolean isZeroRecord(byte[] record) {
            for (byte value : record) {
                if (value != 0) {
                    return false;
                }
            }
            return true;
        }

        private record PaxExtension(
                byte[] header, byte[] payload, Map<String, String> values
        ) {
            private PaxExtension {
                header = header.clone();
                payload = payload.clone();
                values = Map.copyOf(values);
            }

            @Override
            public byte[] header() {
                return header.clone();
            }

            @Override
            public byte[] payload() {
                return payload.clone();
            }
        }
    }

    private static void rejectSymlinkAncestor(String path, Set<String> symlinkPaths) {
        int separator = path.indexOf('/');
        while (separator >= 0) {
            if (symlinkPaths.contains(path.substring(0, separator))) {
                throw new SecurityException(
                        "snapshot archive entry descends through an archive symlink");
            }
            separator = path.indexOf('/', separator + 1);
        }
    }

    private static void recordParentPaths(String path, Set<String> descendantParentPaths) {
        int separator = path.indexOf('/');
        while (separator >= 0) {
            descendantParentPaths.add(path.substring(0, separator));
            separator = path.indexOf('/', separator + 1);
        }
    }

    /** Mirrors DeterministicSnapshotArchiver's root-contained relative-link rule. */
    private static void validateArchiveSymlink(String entryPath, String linkName) {
        if (linkName == null || linkName.isBlank()
                || linkName.getBytes(StandardCharsets.UTF_8).length > MAX_ARCHIVE_PATH_BYTES
                || linkName.indexOf('\0') >= 0 || linkName.contains("\\")) {
            throw new SecurityException("snapshot archive symlink target is invalid");
        }
        Path target = Path.of(linkName);
        if (target.isAbsolute()) {
            throw new SecurityException("snapshot archive symlink target is absolute");
        }
        Path parent = Path.of(entryPath).getParent();
        Path resolved = (parent == null ? Path.of("") : parent).resolve(target).normalize();
        if (resolved.isAbsolute() || resolved.startsWith("..")) {
            throw new SecurityException("snapshot archive symlink escapes its source root");
        }
    }

    private static String validateArchivePath(String value) {
        if (value == null || value.isBlank()
                || value.getBytes(StandardCharsets.UTF_8).length > MAX_ARCHIVE_PATH_BYTES
                || value.startsWith("/") || value.contains("\\")
                || value.indexOf('\0') >= 0) {
            throw new SecurityException("snapshot archive path is invalid");
        }
        String normalized = value.endsWith("/")
                ? value.substring(0, value.length() - 1)
                : value;
        if (normalized.isBlank()) {
            throw new SecurityException("snapshot archive path is invalid");
        }
        for (String segment : normalized.split("/", -1)) {
            if (segment.isBlank() || segment.equals(".") || segment.equals("..")) {
                throw new SecurityException("snapshot archive path traverses directories");
            }
        }
        return normalized;
    }

    record ArchiveInventory(int entryCount, long expandedBytes, long archiveBytes) {
        ArchiveInventory {
            if (entryCount < 0 || expandedBytes < 0 || archiveBytes < expandedBytes) {
                throw new IllegalArgumentException("archive inventory is invalid");
            }
        }
    }

    private void copy(
            String container,
            String target,
            SnapshotSpool spool,
            long maximumDecompressedBytes,
            long expectedArchiveBytes
    ) {
        try (VerifyingArchiveInputStream verified = spool.openVerified();
             ZstdInputStream zstd = new ZstdInputStream(verified);
             BoundedExpandedInputStream tar = new BoundedExpandedInputStream(
                     zstd, maximumDecompressedBytes)) {
            docker.copyArchiveToContainerCmd(container)
                    .withRemotePath(target)
                    .withTarInputStream(tar)
                    .withCopyUIDGID(true)
                    .withDirChildrenOnly(true)
                    .exec();
            if (tar.observedBytes() != expectedArchiveBytes) {
                throw new SecurityException(
                        "Docker did not consume the complete verified snapshot archive");
            }
            // Bind this exact Docker stream to the persisted CAS row as well as the preflight.
            // A path swap cannot affect the fd-backed reader, and an in-place mutation cannot
            // pass this digest/size check.
            verified.requireComplete();
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("snapshot materialization failed", error);
        }
    }

    /**
     * Opens the deployment reader exactly once and freezes its bytes in an owner-only spool.
     * Every later verification and Docker copy reads a positional view of the retained descriptor
     * rather than reopening a mutable legacy source path, spool path, or provider stream.
     */
    static SnapshotSpool spoolArchive(
            WorkspaceInfrastructurePorts.SnapshotArtifactReader reader,
            WorkspaceInfrastructurePorts.SnapshotArtifact archive,
            long maximumCompressedBytes
    ) throws IOException {
        Objects.requireNonNull(reader, "reader");
        Objects.requireNonNull(archive, "archive");
        if (maximumCompressedBytes < 1 || archive.sizeBytes() > maximumCompressedBytes) {
            throw new SecurityException("snapshot compressed size exceeds workspace policy");
        }
        Path directory = null;
        Path spool = null;
        FileChannel frozenChannel = null;
        try {
            directory = Files.createTempDirectory(
                    "elmos-snapshot-spool-",
                    PosixFilePermissions.asFileAttribute(PRIVATE_DIRECTORY_PERMISSIONS));
            spool = directory.resolve("snapshot.tar.zst");
            Set<OpenOption> spoolOptions = Set.of(
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    LinkOption.NOFOLLOW_LINKS);
            frozenChannel = FileChannel.open(
                    spool,
                    spoolOptions,
                    PosixFilePermissions.asFileAttribute(PRIVATE_SPOOL_WRITE_PERMISSIONS));
            BasicFileAttributes created = Files.readAttributes(
                    spool, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!created.isRegularFile() || created.isSymbolicLink()
                    || created.fileKey() == null) {
                throw new SecurityException("snapshot spool inode was not created safely");
            }
            try (InputStream source = reader.open(archive);
                 VerifyingArchiveInputStream verified = new VerifyingArchiveInputStream(
                         source, archive.sha256(), archive.sizeBytes())) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = verified.read(buffer)) != -1) {
                    if (read > 0) {
                        ByteBuffer bytes = ByteBuffer.wrap(buffer, 0, read);
                        while (bytes.hasRemaining()) {
                            frozenChannel.write(bytes);
                        }
                    }
                }
                verified.requireComplete();
            }
            frozenChannel.force(false);
            if (frozenChannel.size() != archive.sizeBytes()) {
                throw new SecurityException("snapshot spool size changed while freezing");
            }
            Files.setPosixFilePermissions(spool, PRIVATE_SPOOL_READ_PERMISSIONS);
            SnapshotSpool captured = SnapshotSpool.capture(
                    directory,
                    spool,
                    frozenChannel,
                    created.fileKey(),
                    archive.sha256(),
                    archive.sizeBytes());
            frozenChannel = null; // ownership transferred to SnapshotSpool
            return captured;
        } catch (IOException | RuntimeException error) {
            if (frozenChannel != null) {
                try {
                    frozenChannel.close();
                } catch (IOException closeFailure) {
                    error.addSuppressed(closeFailure);
                }
            }
            IOException cleanup = deleteSpool(spool, directory);
            if (cleanup != null) {
                error.addSuppressed(cleanup);
            }
            throw error;
        }
    }

    private static IOException deleteSpool(Path spool, Path directory) {
        IOException failure = null;
        if (spool != null) {
            try {
                Files.deleteIfExists(spool);
            } catch (IOException error) {
                failure = error;
            }
        }
        if (directory != null) {
            try {
                Files.deleteIfExists(directory);
            } catch (IOException error) {
                if (failure == null) {
                    failure = error;
                } else {
                    failure.addSuppressed(error);
                }
            }
        }
        return failure;
    }

    static final class SnapshotSpool implements AutoCloseable {
        private final Path directory;
        private final Path spool;
        private final FileChannel frozenChannel;
        private final String expectedSha256;
        private final long expectedSize;
        private boolean closed;

        private SnapshotSpool(
                Path directory,
                Path spool,
                FileChannel frozenChannel,
                String expectedSha256,
                long expectedSize
        ) {
            this.directory = directory;
            this.spool = spool;
            this.frozenChannel = frozenChannel;
            this.expectedSha256 = expectedSha256;
            this.expectedSize = expectedSize;
        }

        static SnapshotSpool capture(
                Path directory,
                Path spool,
                FileChannel frozenChannel,
                Object expectedFileKey,
                String expectedSha256,
                long expectedSize
        ) throws IOException {
            if (!frozenChannel.isOpen() || frozenChannel.size() != expectedSize) {
                throw new SecurityException("snapshot spool channel is not stable");
            }
            BasicFileAttributes attributes = Files.readAttributes(
                    spool, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!attributes.isRegularFile() || attributes.isSymbolicLink()
                    || attributes.size() != expectedSize || attributes.fileKey() == null
                    || !expectedFileKey.equals(attributes.fileKey())) {
                throw new SecurityException("snapshot spool identity is not stable");
            }
            return new SnapshotSpool(
                    directory, spool, frozenChannel, expectedSha256, expectedSize);
        }

        InputStream open() throws IOException {
            if (closed || !frozenChannel.isOpen()) {
                throw new IllegalStateException("snapshot spool is closed");
            }
            // Positional readers share the already-open descriptor but maintain independent
            // offsets.  No later path lookup can redirect a copy to a replacement inode.
            return new PositionalChannelInputStream(frozenChannel);
        }

        VerifyingArchiveInputStream openVerified() throws IOException {
            return new VerifyingArchiveInputStream(open(), expectedSha256, expectedSize);
        }

        @Override
        public void close() throws IOException {
            if (!closed) {
                closed = true;
                IOException failure = null;
                try {
                    frozenChannel.close();
                } catch (IOException closeFailure) {
                    failure = closeFailure;
                }
                IOException cleanup = deleteSpool(spool, directory);
                if (cleanup != null) {
                    if (failure == null) {
                        failure = cleanup;
                    } else {
                        failure.addSuppressed(cleanup);
                    }
                }
                if (failure != null) {
                    throw failure;
                }
            }
        }
    }

    /** A close-isolated view over one retained inode; reads never resolve the spool path again. */
    static final class PositionalChannelInputStream extends InputStream {
        private final FileChannel channel;
        private long position;
        private boolean closed;

        PositionalChannelInputStream(FileChannel channel) {
            this.channel = Objects.requireNonNull(channel, "channel");
        }

        @Override
        public int read() throws IOException {
            byte[] single = new byte[1];
            int read = read(single, 0, 1);
            return read < 0 ? -1 : Byte.toUnsignedInt(single[0]);
        }

        @Override
        public int read(byte[] bytes, int offset, int length) throws IOException {
            Objects.checkFromIndexSize(offset, length, bytes.length);
            requireOpen();
            if (length == 0) {
                return 0;
            }
            int read = channel.read(ByteBuffer.wrap(bytes, offset, length), position);
            if (read > 0) {
                position += read;
            }
            return read;
        }

        @Override
        public int available() throws IOException {
            requireOpen();
            return Math.toIntExact(Math.min(
                    Integer.MAX_VALUE, Math.max(0L, channel.size() - position)));
        }

        @Override
        public void close() {
            closed = true;
        }

        private void requireOpen() throws IOException {
            if (closed || !channel.isOpen()) {
                throw new IOException("snapshot spool reader is closed");
            }
        }
    }

    static WorkspaceInfrastructurePorts.SnapshotArtifact requireBoundArtifact(
            WorkspaceModels.WorkspaceRequest request,
            WorkspaceInfrastructurePorts.SnapshotArtifact artifact
    ) {
        Objects.requireNonNull(request, "request");
        Objects.requireNonNull(artifact, "artifact");
        if (!request.organizationId().equals(artifact.organizationId())
                || !request.migrationRunId().equals(artifact.migrationRunId())
                || !request.snapshotId().equals(artifact.snapshotId())) {
            throw new SecurityException(
                    "snapshot artifact resource binding does not match workspace request");
        }
        return artifact;
    }

    static Map<String, String> helperLabels(
            WorkspaceModels.WorkspaceRequest request,
            WorkspaceInfrastructurePorts.SnapshotArtifact archive
    ) {
        Objects.requireNonNull(request, "request");
        Objects.requireNonNull(archive, "archive");
        return Map.of(
                "elmos.managed", "true",
                "elmos.organization_id", archive.organizationId(),
                "elmos.workspace_id", request.workspaceId(),
                "elmos.migration_run_id", archive.migrationRunId(),
                "elmos.repository_id", archive.repositoryId(),
                "elmos.snapshot_id", archive.snapshotId(),
                "elmos.resource_role", "snapshot-materializer",
                "elmos.retention", "ephemeral");
    }

    /** Counts and rejects decompressed bytes before any tar parser or Docker consumer sees them. */
    static final class BoundedExpandedInputStream extends FilterInputStream {
        private final long maximumBytes;
        private long observedBytes;

        BoundedExpandedInputStream(InputStream input, long maximumBytes) {
            super(Objects.requireNonNull(input, "input"));
            if (maximumBytes < 1) {
                throw new IllegalArgumentException("expanded archive limit must be positive");
            }
            this.maximumBytes = maximumBytes;
        }

        @Override
        public int read() throws IOException {
            int value = super.read();
            if (value >= 0) {
                observe(1);
            }
            return value;
        }

        @Override
        public int read(byte[] bytes, int offset, int length) throws IOException {
            int read = super.read(bytes, offset, length);
            if (read > 0) {
                observe(read);
            }
            return read;
        }

        @Override
        public long skip(long count) throws IOException {
            if (count <= 0) {
                return 0;
            }
            byte[] buffer = new byte[(int) Math.min(count, 8192)];
            long skipped = 0;
            while (skipped < count) {
                int read = read(buffer, 0, (int) Math.min(buffer.length, count - skipped));
                if (read < 0) {
                    break;
                }
                skipped += read;
            }
            return skipped;
        }

        long observedBytes() {
            return observedBytes;
        }

        private void observe(int count) {
            if (observedBytes > maximumBytes - count) {
                throw new SecurityException(
                        "snapshot archive decompressed size exceeds policy");
            }
            observedBytes += count;
        }
    }

    /**
     * Verifies the persisted digest and size while an artifact is frozen or preflighted. This
     * binds the private spool to the immutable database row and protects the legacy compatibility
     * reader from returning replacement bytes after its own pre-read verification.
     */
    static final class VerifyingArchiveInputStream extends FilterInputStream {
        private final MessageDigest digest;
        private final String expectedSha256;
        private final long expectedSize;
        private long observedSize;

        VerifyingArchiveInputStream(InputStream input, String expectedSha256, long expectedSize) {
            super(Objects.requireNonNull(input, "input"));
            if (expectedSha256 == null || !expectedSha256.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("expected archive digest is invalid");
            }
            if (expectedSize < 0) {
                throw new IllegalArgumentException("expected archive size is invalid");
            }
            this.expectedSha256 = expectedSha256;
            this.expectedSize = expectedSize;
            try {
                this.digest = MessageDigest.getInstance("SHA-256");
            } catch (Exception unavailable) {
                throw new IllegalStateException("SHA-256 is unavailable", unavailable);
            }
        }

        @Override
        public int read() throws IOException {
            int value = super.read();
            if (value >= 0) {
                observe(new byte[]{(byte) value}, 0, 1);
            }
            return value;
        }

        @Override
        public int read(byte[] bytes, int offset, int length) throws IOException {
            int read = super.read(bytes, offset, length);
            if (read > 0) {
                observe(bytes, offset, read);
            }
            return read;
        }

        @Override
        public long skip(long count) throws IOException {
            if (count <= 0) {
                return 0;
            }
            byte[] buffer = new byte[(int) Math.min(count, 8192)];
            long skipped = 0;
            while (skipped < count) {
                int read = read(buffer, 0, (int) Math.min(buffer.length, count - skipped));
                if (read < 0) {
                    break;
                }
                skipped += read;
            }
            return skipped;
        }

        void requireComplete() {
            String actual = HexFormat.of().formatHex(digest.digest());
            if (observedSize != expectedSize || !actual.equals(expectedSha256)) {
                throw new SecurityException("snapshot archive digest or size mismatch");
            }
        }

        private void observe(byte[] bytes, int offset, int length) {
            observedSize += length;
            if (observedSize > expectedSize) {
                throw new SecurityException("snapshot archive exceeds its declared size");
            }
            digest.update(bytes, offset, length);
        }
    }
}
