package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.integrations.GitRepositoryWorkspaceService;
import io.elmos.storage.S3ObjectStore;
import io.elmos.workflow.ExecutionJobPort;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/** Host-only repository/cases capture. Source bytes never become PostgreSQL job JSON. */
@Component
final class TranslationExecutionPreparation {
    static final String KIND = "translate-pipeline-v1";
    private final ObjectProvider<GitRepositoryWorkspaceService> workspaces;
    private final ArtifactController.ObjectStoreFactory stores;
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;
    private final String casesRoot;
    private final String repositoryRoot;
    private final boolean billingEnforced;
    @Value("${elmos.translation.node-executable:}")
    private String nodeExecutable = "";
    private final java.util.concurrent.Semaphore preparationSlots = new java.util.concurrent.Semaphore(2);
    private final java.util.Set<String> preparingTenants = java.util.concurrent.ConcurrentHashMap.newKeySet();

    TranslationExecutionPreparation(ObjectProvider<GitRepositoryWorkspaceService> workspaces,
            ArtifactController.ObjectStoreFactory stores, JdbcClient jdbc,
            TransactionTemplate billingTransactionTemplate, ObjectMapper json,
            @Value("${elmos.translation.cases-root:}") String casesRoot,
            @Value("${elmos.translation.repository-root:}") String repositoryRoot,
            @Value("${ELMOS_BILLING_ENFORCEMENT_ENABLED:${elmos.billing.enforcement-enabled:false}}") boolean billingEnforced) {
        this.workspaces = workspaces; this.stores = stores; this.jdbc = jdbc;
        this.transactions = billingTransactionTemplate; this.json = json;
        this.casesRoot = casesRoot; this.repositoryRoot = repositoryRoot;
        this.billingEnforced = billingEnforced;
    }

    Map<String, Object> prepare(ControlPlanePrincipal principal, Map<String, Object> request, String key) {
        principal.require(principal.organizationId(), principal.actorId(), "translation:execute");
        principal.require(principal.organizationId(), principal.actorId(), "repository:read");
        if (!preparationSlots.tryAcquire()) fail("TRANSLATION_INPUT_CAPACITY_EXCEEDED");
        boolean admitted = preparingTenants.add(principal.organizationId());
        try {
            if (!admitted) fail("TRANSLATION_INPUT_TENANT_CAPACITY_EXCEEDED");
            return prepareAdmitted(principal, request, key);
        } finally {
            if (admitted) preparingTenants.remove(principal.organizationId());
            preparationSlots.release();
        }
    }

    void requireSubmissionConfiguration() {
        requireRuntimeAuthority();
        try {
            trustedDirectory(casesRoot); trustedDirectory(repositoryRoot); stores.current();
            if (!Path.of(nodeExecutable).isAbsolute() || !Files.isExecutable(Path.of(nodeExecutable)))
                fail("TRANSLATION_ADMISSION_RUNTIME_REQUIRED");
        }
        catch (Exception error) { fail("TRANSLATION_HOSTED_CONFIGURATION_REQUIRED"); }
        if (workspaces.getIfAvailable() == null) fail("TRANSLATION_REPOSITORY_SERVICE_REQUIRED");
    }

    private Map<String, Object> prepareAdmitted(ControlPlanePrincipal principal, Map<String, Object> request, String key) {
        // The existing wallet and the legacy credit producer are different price
        // contracts. Until an approved host adapter exists, never double-charge
        // or silently substitute one for the other.
        if (billingEnforced) fail("TRANSLATION_HOSTED_BILLING_CONTRACT_REQUIRED");
        requireRuntimeAuthority();
        if (!request.keySet().equals(java.util.Set.of("repositoryWorkspaceId", "casesBundleId", "sourceLanguage", "targetLanguage"))) {
            fail("TRANSLATION_HOSTED_REQUEST_INVALID");
        }
        String workspaceId = identifier(request.get("repositoryWorkspaceId"));
        try {
            if (!UUID.fromString(workspaceId).toString().equals(workspaceId)) fail("TRANSLATION_WORKSPACE_INVALID");
        } catch (IllegalArgumentException error) { fail("TRANSLATION_WORKSPACE_INVALID"); }
        String bundleId = identifier(request.get("casesBundleId"));
        String source = identifier(request.get("sourceLanguage"));
        String target = identifier(request.get("targetLanguage"));
        Map<String, Object> gate = gate(source, target);
        var service = workspaces.getIfAvailable();
        if (service == null) fail("TRANSLATION_REPOSITORY_SERVICE_REQUIRED");
        var snapshot = service.inspect(principal.organizationId(), principal.actorId(), workspaceId);
        if (!snapshot.completeness().name().equals("COMPLETE") || !snapshot.pendingPaths().isEmpty()) {
            fail("REPOSITORY_TRANSLATION_SOURCE_NOT_IMMUTABLE");
        }
        Map<String, Object> subject = new LinkedHashMap<>();
        subject.put("schemaVersion", "translation-input-v1");
        subject.put("tenantId", principal.organizationId());
        subject.put("actor", principal.actorId());
        subject.put("repositoryWorkspaceId", workspaceId);
        subject.put("repositoryRef", "repository-workspace:" + workspaceId + "@" + snapshot.currentHeadCommit());
        subject.put("sourceCommit", snapshot.currentHeadCommit());
        subject.put("sourceLanguage", source); subject.put("targetLanguage", target);
        subject.put("casesBundleId", bundleId); subject.putAll(gate);
        Path temporary = null;
        try {
            temporary = Files.createTempDirectory("elmos-translation-input-");
            Path archive = temporary.resolve("input.zip");
            List<Map<String, Object>> files = new ArrayList<>();
            long total = 0;
            try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(archive))) {
                int sourceCount = 0;
                for (var file : snapshot.files()) {
                    if (file.category().name().equals("SOURCE") && !file.readable()) fail("REPOSITORY_TRANSLATION_PROTECTED_SOURCE_EXCLUDED");
                    if (!file.readable() || !java.util.Set.of("SOURCE", "DOCUMENTATION", "CONFIGURATION", "TEST").contains(file.category().name())) continue;
                    if (++sourceCount > 1000) fail("REPOSITORY_TRANSLATION_SCOPE_EXCEEDED");
                    var content = service.readFile(principal.organizationId(), principal.actorId(), workspaceId, file.path());
                    byte[] bytes = content.content().getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    if (bytes.length != file.bytes() || !sha(bytes).equals(file.sha256())) fail("TRANSLATION_SOURCE_CHANGED");
                    total += bytes.length;
                    if (total > 64L * 1024 * 1024) fail("REPOSITORY_TRANSLATION_SCOPE_EXCEEDED");
                    add(zip, files, "source/" + file.path(), bytes);
                }
                if (sourceCount == 0) fail("TRANSLATION_SOURCE_EMPTY");
                Path root = trustedDirectory(casesRoot);
                Path cases = root.resolve(principal.organizationId()).resolve(bundleId).normalize();
                if (!cases.startsWith(root) || !cases.toRealPath().equals(cases)) fail("TRANSLATION_CASES_PATH_INVALID");
                int count = 0;
                long caseBytes = 0;
                try (var children = Files.list(cases)) {
                    for (Path file : children.limit(10_001).sorted().toList()) {
                        if (++count > 10_000 || !file.getFileName().toString().matches("WU-[0-9]{5}\\.json")) fail("TRANSLATION_CASES_INVALID");
                        byte[] bytes = stableBytes(file, 1024 * 1024);
                        if (!json.readTree(bytes).isArray()) fail("TRANSLATION_CASES_INVALID");
                        caseBytes += bytes.length;
                        if (caseBytes > 16L * 1024 * 1024) fail("TRANSLATION_CASES_SIZE_LIMIT");
                        add(zip, files, "cases/" + file.getFileName(), bytes);
                    }
                }
                if (count == 0) fail("TRANSLATION_CASES_EMPTY");
                var after = service.inspect(principal.organizationId(), principal.actorId(), workspaceId);
                if (!after.currentHeadCommit().equals(snapshot.currentHeadCommit()) || !after.pendingPaths().isEmpty()) fail("TRANSLATION_SOURCE_CHANGED");
                Map<String, Object> manifest = new LinkedHashMap<>(subject); manifest.put("files", files);
                put(zip, "manifest.json", json.writeValueAsBytes(manifest));
            }
            String digest;
            try (var input = Files.newInputStream(archive)) {
                MessageDigest hashing = MessageDigest.getInstance("SHA-256");
                byte[] buffer = new byte[64 * 1024]; int n;
                while ((n = input.read(buffer)) != -1) hashing.update(buffer, 0, n);
                digest = HexFormat.of().formatHex(hashing.digest());
            }
            long byteSize = Files.size(archive);
            S3ObjectStore store = stores.current();
            var ticket = store.presignUpload(principal.organizationId(), digest, byteSize, "application/zip", Duration.ofMinutes(5));
            String binding = transactions.execute(status -> {
                jdbc.sql("SELECT set_config('app.organization_id', :org, true)").param("org", principal.organizationId()).query(String.class).single();
                return jdbc.sql("SELECT elmos_prepare_execution_input(:id, :org, :key, :object, :sha, :bytes)")
                        .param("id", "input-" + UUID.randomUUID()).param("org", principal.organizationId())
                        .param("key", key).param("object", ticket.contentObjectId()).param("sha", digest).param("bytes", byteSize)
                        .query(String.class).single();
            });
            var upload = HttpRequest.newBuilder(ticket.uploadUrl()).timeout(Duration.ofMinutes(2))
                    .PUT(HttpRequest.BodyPublishers.ofFile(archive));
            ticket.requiredHeaders().forEach(upload::header);
            var response = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).build()
                    .send(upload.build(), HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() / 100 != 2 || !store.verifyUpload(principal.organizationId(), ticket.contentObjectId(), digest, byteSize)) {
                fail("TRANSLATION_INPUT_UPLOAD_UNCONFIRMED");
            }
            subject.put("input", Map.of("bindingId", binding, "objectId", ticket.contentObjectId(), "sha256", digest, "byteSize", byteSize));
            return Map.copyOf(subject);
        } catch (ExecutionJobPort.ExecutionStateException error) { throw error; }
        catch (Exception error) { throw new ExecutionJobPort.ExecutionStateException("TRANSLATION_INPUT_PREPARATION_FAILED"); }
        finally {
            if (temporary != null) try { Files.deleteIfExists(temporary.resolve("input.zip")); Files.deleteIfExists(temporary); } catch (IOException ignored) { /* operator-visible temporary spool remains */ }
        }
    }

    private void requireRuntimeAuthority() {
        if(billingEnforced)fail("TRANSLATION_HOSTED_BILLING_CONTRACT_REQUIRED");
        if(!jdbc.sql("""
            SELECT has_table_privilege(current_user,'public.execution_input_bindings','SELECT')
                AND has_function_privilege(current_user,'public.elmos_prepare_execution_input(varchar,varchar,varchar,varchar,varchar,bigint)','EXECUTE')
                AND has_function_privilege(current_user,'public.elmos_attach_execution_input(varchar,varchar,varchar)','EXECUTE')
                AND has_function_privilege(current_user,'public.elmos_translation_billing_guard()','EXECUTE')
            """).query(Boolean.class).single()) fail("TRANSLATION_RUNTIME_DATABASE_AUTHORITY_REQUIRED");
        // This preflight avoids effects under an already enabled wallet. The
        // enqueue transaction repeats and holds the guard to close a later flip.
        jdbc.sql("SELECT elmos_translation_billing_guard()").query(Boolean.class).single();
    }

    void attach(String organization, String job, Map<String, Object> payload) {
        Object raw = payload.get("input");
        if (!(raw instanceof Map<?, ?> input)) fail("TRANSLATION_INPUT_MISSING");
        transactions.executeWithoutResult(status -> {
            jdbc.sql("SELECT set_config('app.organization_id', :org, true)").param("org", organization).query(String.class).single();
            jdbc.sql("SELECT elmos_attach_execution_input(:org, :job, :binding)")
                    .param("org", organization).param("job", job).param("binding", ((Map<?, ?>) raw).get("bindingId"))
                    .query(Boolean.class).single();
        });
    }

    String enqueue(ExecutionJobPort jobs, ExecutionJobPort.EnqueueCommand command) {
        return transactions.execute(status -> {
            // Holds the actual DB billing switch row through admission/commit;
            // the legacy Node flag alone cannot establish an unbilled contract.
            jdbc.sql("SELECT elmos_translation_billing_guard()").query(Boolean.class).single();
            String job = jobs.enqueue(command);
            attach(command.organizationId(), job, command.requestPayload());
            return job;
        });
    }

    private Map<String, Object> gate(String source, String target) {
        Process process = null;
        java.util.concurrent.ScheduledExecutorService deadlines = null;
        try {
            Path root = trustedDirectory(repositoryRoot);
            Path node = Path.of(nodeExecutable);
            if (!node.isAbsolute() || !Files.isRegularFile(node) || !Files.isExecutable(node)) fail("TRANSLATION_ADMISSION_RUNTIME_REQUIRED");
            ProcessBuilder builder = new ProcessBuilder(node.toString(), "--no-warnings", "--loader",
                    root.resolve("apps/translation-runtime-runner/ts-loader.mjs").toString(),
                    root.resolve("apps/translation-runtime-runner/admission.mjs").toString(), source, target);
            builder.directory(root.toFile()).redirectErrorStream(true);
            builder.environment().clear();
            builder.environment().put("ELMOS_REPOSITORY_ROOT", root.toString());
            builder.environment().put("NODE_ENV", "production");
            process = builder.start();
            process.getOutputStream().close();
            Process child = process;
            deadlines = java.util.concurrent.Executors.newSingleThreadScheduledExecutor(r -> {
                Thread thread = new Thread(r, "translation-admission-deadline"); thread.setDaemon(true); return thread;
            });
            deadlines.schedule(child::destroyForcibly, 30, java.util.concurrent.TimeUnit.SECONDS);
            byte[] bytes;
            try (var output = process.getInputStream()) { bytes = output.readNBytes(64 * 1024 + 1); }
            if (bytes.length > 64 * 1024) fail("TRANSLATION_ROUTE_ADMISSION_OUTPUT_LIMIT");
            if (!process.waitFor(5, java.util.concurrent.TimeUnit.SECONDS) || process.exitValue() != 0)
                fail("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE");
            var result = json.readTree(bytes);
            if (!result.path("repositoryExecutionStatus").asText().equals("PASSED")
                    || !result.path("repositoryProfile").asText().equals("typed-pure-function-v1")
                    || !result.path("repositoryEvidenceSha256").asText().matches("[a-f0-9]{64}")
                    || !result.path("repositoryEvidenceBytes").canConvertToLong()
                    || result.path("repositoryEvidenceBytes").asLong() < 1)
                fail("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE");
            return json.convertValue(result, new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>() {});
        } catch (ExecutionJobPort.ExecutionStateException error) { throw error; }
        catch (Exception error) { throw new ExecutionJobPort.ExecutionStateException("TRANSLATION_ROUTE_NOT_REPOSITORY_EXECUTABLE"); }
        finally {
            if (deadlines != null) deadlines.shutdownNow();
            if (process != null && process.isAlive()) {
                // This trusted gate is read-only. Keep its preparation slot
                // until the killed process is actually reaped.
                process.destroyForcibly();
                boolean interrupted=false;
                while(process.isAlive()) {
                    try {process.waitFor();} catch(InterruptedException error) {interrupted=true;}
                }
                if(interrupted)Thread.currentThread().interrupt();
            }
        }
    }

    private static Path trustedDirectory(String value) throws IOException {
        if (value == null || value.isBlank()) throw new IOException("TRANSLATION_DIRECTORY_NOT_CONFIGURED");
        Path root = Path.of(value).normalize();
        if (!root.isAbsolute() || root.getParent() == null || !root.toRealPath().equals(root)) throw new IOException("TRANSLATION_DIRECTORY_INVALID");
        return root;
    }
    private static String identifier(Object value) {
        if (!(value instanceof String text) || !text.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")) fail("TRANSLATION_IDENTIFIER_INVALID");
        return (String) value;
    }
    private static void safePath(String path) throws IOException {
        if (path.isBlank() || path.length() > 1024 || path.startsWith("/") || path.contains("\\")
                || path.chars().anyMatch(c -> c < 32 || c == 127)) throw new IOException("TRANSLATION_PATH_UNSAFE");
        for (String part : path.split("/", -1)) if (part.isEmpty() || part.equals(".") || part.equals("..")) throw new IOException("TRANSLATION_PATH_UNSAFE");
    }
    private static byte[] stableBytes(Path file, int maximum) throws IOException {
        var before = Files.readAttributes(file, java.nio.file.attribute.BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!before.isRegularFile() || before.size() < 1 || before.size() > maximum || !file.toRealPath().equals(file.toAbsolutePath())) throw new IOException("TRANSLATION_FILE_UNSAFE");
        byte[] bytes;
        try (var stream = Files.newInputStream(file, LinkOption.NOFOLLOW_LINKS)) { bytes = stream.readNBytes(maximum + 1); }
        var after = Files.readAttributes(file, java.nio.file.attribute.BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (bytes.length != before.size() || !java.util.Objects.equals(before.fileKey(), after.fileKey())
                || !before.lastModifiedTime().equals(after.lastModifiedTime()) || before.size() != after.size()) throw new IOException("TRANSLATION_FILE_CHANGED");
        return bytes;
    }
    private static void add(ZipOutputStream zip, List<Map<String, Object>> files, String path, byte[] bytes) throws Exception {
        safePath(path); put(zip, path, bytes); files.add(Map.of("path", path, "bytes", bytes.length, "sha256", sha(bytes)));
    }
    private static void put(ZipOutputStream zip, String name, byte[] bytes) throws IOException {
        ZipEntry entry = new ZipEntry(name); entry.setTime(0); zip.putNextEntry(entry); zip.write(bytes); zip.closeEntry();
    }
    private static String sha(byte[] bytes) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
    private static void fail(String code) { throw new ExecutionJobPort.ExecutionStateException(code); }
}
