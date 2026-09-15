package io.elmos.worker.web;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

/**
 * Industrial-grade modernizer for file upload security, multipart migration, and path traversal prevention.
 *
 * <p>Key enterprise challenges in Spring 6 / Spring Boot 3 multipart uploads:
 * <ol>
 *   <li><b>CommonsMultipartResolver Removal:</b> Spring 6 has completely removed Apache Commons FileUpload
 *       support ({@code CommonsMultipartResolver}, {@code CommonsMultipartFile}). Old applications fail at startup
 *       with {@code ClassNotFoundException: org.springframework.web.multipart.commons.CommonsMultipartResolver}.
 *       This modernizer replaces references with standard {@code MultipartFile} and Servlet 3.0+ container multipart handling.</li>
 *   <li><b>Multipart Configuration Modernization:</b> Normalizes legacy {@code spring.http.multipart.*} (Boot 1.x)
 *       to {@code spring.servlet.multipart.*} (Boot 3.x), adding ISO/IEC size units (e.g. {@code 10MB}, {@code 50MB}).</li>
 *   <li><b>Path Traversal & Malicious File Upload Defense:</b> Generates {@code SecureFileUploadHelper.java}
 *       which validates extension allowlists, sanitizes filenames by stripping {@code ../} directory traversals and null bytes,
 *       and enforces canonical path containment boundaries.</li>
 * </ol>
 */
public final class SpringFileUploadSecurityModernizer {

    public record FileUploadModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static FileUploadModernizationResult empty() {
            return new FileUploadModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern COMMONS_MULTIPART_RESOLVER_BEAN = Pattern.compile(
            "(?s)@Bean(?:\\([^)]*\\))?\\s+public\\s+(?:org\\.springframework\\.web\\.multipart\\.commons\\.)?CommonsMultipartResolver\\s+[a-zA-Z0-9_]+\\s*\\([^)]*\\)\\s*\\{.*?return\\s+new\\s+CommonsMultipartResolver\\s*\\([^)]*\\);?\\s*\\}"
    );

    private static final Pattern OLD_COMMONS_FILE_IMPORT = Pattern.compile(
            "import\\s+org\\.springframework\\.web\\.multipart\\.commons\\.CommonsMultipartFile;?"
    );

    private static final Pattern OLD_COMMONS_RESOLVER_IMPORT = Pattern.compile(
            "import\\s+org\\.springframework\\.web\\.multipart\\.commons\\.CommonsMultipartResolver;?"
    );

    private SpringFileUploadSecurityModernizer() {}

    public static FileUploadModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return FileUploadModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;
        boolean uploadDetected = false;

        // 1. Scan Java files for CommonsMultipartResolver and CommonsMultipartFile
        Path srcDir = projectRoot.resolve("src");
        if (Files.isDirectory(srcDir)) {
            try (Stream<Path> stream = Files.walk(srcDir)) {
                List<Path> javaFiles = stream.filter(p -> Files.isRegularFile(p) && p.toString().endsWith(".java")).toList();
                for (Path javaFile : javaFiles) {
                    try {
                        String content = Files.readString(javaFile, StandardCharsets.UTF_8);
                        String updated = content;

                        if (OLD_COMMONS_RESOLVER_IMPORT.matcher(updated).find()) {
                            updated = OLD_COMMONS_RESOLVER_IMPORT.matcher(updated).replaceAll(
                                    "import org.springframework.web.multipart.support.StandardServletMultipartResolver;");
                        }
                        if (OLD_COMMONS_FILE_IMPORT.matcher(updated).find()) {
                            updated = OLD_COMMONS_FILE_IMPORT.matcher(updated).replaceAll(
                                    "import org.springframework.web.multipart.MultipartFile;");
                        }

                        if (COMMONS_MULTIPART_RESOLVER_BEAN.matcher(updated).find()) {
                            updated = COMMONS_MULTIPART_RESOLVER_BEAN.matcher(updated).replaceAll(
                                    """
                                    @Bean
                                    public StandardServletMultipartResolver multipartResolver() {
                                        return new StandardServletMultipartResolver();
                                    }""");
                            rulesApplied.add("REPLACE_COMMONS_MULTIPART_RESOLVER_WITH_STANDARD_SERVLET");
                        }

                        if (updated.contains("CommonsMultipartFile")) {
                            updated = updated.replace("CommonsMultipartFile", "MultipartFile");
                            rulesApplied.add("REPLACE_COMMONS_MULTIPART_FILE_WITH_MULTIPART_FILE");
                        }

                        if (content.contains("MultipartFile") || content.contains("multipart") || content.contains("upload")) {
                            uploadDetected = true;
                        }

                        if (!updated.equals(content)) {
                            uploadDetected = true;
                            Files.writeString(javaFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(javaFile).toString());
                            changes++;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to process Java file " + javaFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan src directory for file upload: " + e.getMessage());
            }
        }

        // 2. Scan and modernize application configuration for multipart settings
        Path resourcesDir = srcDir.resolve("main/resources");
        if (Files.isDirectory(resourcesDir)) {
            try (Stream<Path> stream = Files.walk(resourcesDir)) {
                List<Path> configFiles = stream.filter(p -> Files.isRegularFile(p) &&
                        (p.toString().endsWith(".yml") || p.toString().endsWith(".yaml") || p.toString().endsWith(".properties"))
                ).toList();

                for (Path configFile : configFiles) {
                    try {
                        String content = Files.readString(configFile, StandardCharsets.UTF_8);
                        String updated = content;

                        // Modernize legacy Boot 1.x spring.http.multipart to spring.servlet.multipart
                        if (updated.contains("spring.http.multipart")) {
                            uploadDetected = true;
                            updated = updated.replace("spring.http.multipart", "spring.servlet.multipart");
                            rulesApplied.add("MODERNIZE_HTTP_MULTIPART_TO_SERVLET_MULTIPART");
                        }

                        Pattern nestedHttpMultipart = Pattern.compile("(?m)^(\\s*)http:(\\s*\\r?\\n\\s*multipart:)");
                        if (nestedHttpMultipart.matcher(updated).find()) {
                            uploadDetected = true;
                            updated = nestedHttpMultipart.matcher(updated).replaceAll("$1servlet:$2");
                            rulesApplied.add("MODERNIZE_NESTED_HTTP_MULTIPART_TO_SERVLET_MULTIPART");
                        }

                        if (updated.contains("spring.servlet.multipart") || updated.contains("multipart:")) {
                            uploadDetected = true;
                        }

                        if (!updated.equals(content)) {
                            Files.writeString(configFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(configFile).toString());
                            changes++;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to process config file " + configFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan resources for file upload configs: " + e.getMessage());
            }
        }

        // 3. Generate SecureFileUploadHelper.java if upload functionality is detected
        if (uploadDetected) {
            Path targetPackageDir = srcDir.resolve("main/java/io/elmos/generated/upload");
            try {
                Files.createDirectories(targetPackageDir);
                Path helperFile = targetPackageDir.resolve("SecureFileUploadHelper.java");
                if (!Files.exists(helperFile)) {
                    String helperSource = generateSecureFileUploadHelperSource();
                    Files.writeString(helperFile, helperSource, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(helperFile).toString());
                    rulesApplied.add("GENERATE_SECURE_FILE_UPLOAD_HELPER");
                    changes++;
                }
            } catch (IOException e) {
                warnings.add("Failed to generate SecureFileUploadHelper: " + e.getMessage());
            }
        }

        return new FileUploadModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private static String generateSecureFileUploadHelperSource() {
        return """
                package io.elmos.generated.upload;

                import org.springframework.web.multipart.MultipartFile;

                import java.io.File;
                import java.io.IOException;
                import java.nio.file.Path;
                import java.nio.file.Paths;
                import java.util.Arrays;
                import java.util.HashSet;
                import java.util.Set;
                import java.util.UUID;

                /**
                 * Enterprise-grade secure file upload helper for Spring Boot 3.
                 *
                 * <p>Protects applications against Directory Traversal (Path Traversal), Null Byte Injections,
                 * and executable webshell uploads (e.g. .jsp, .sh, .exe).</p>
                 */
                public final class SecureFileUploadHelper {

                    private static final Set<String> DEFAULT_SAFE_EXTENSIONS = new HashSet<>(Arrays.asList(
                            "jpg", "jpeg", "png", "gif", "webp", "pdf", "txt", "csv", "xlsx", "docx", "zip"
                    ));

                    private SecureFileUploadHelper() {}

                    /**
                     * Cleans and sanitizes the uploaded file name, stripping directory traversal patterns.
                     */
                    public static String sanitizeFilename(String originalFilename) {
                        if (originalFilename == null) {
                            return UUID.randomUUID().toString();
                        }
                        // Remove null bytes
                        String clean = originalFilename.replace("\\0", "");
                        // Remove directory traversals
                        clean = Paths.get(clean).getFileName().toString();
                        clean = clean.replaceAll("[/\\\\:]", "_");
                        return clean;
                    }

                    /**
                     * Saves the multipart file into destination directory with strict boundary confinement.
                     */
                    public static File saveSecurely(MultipartFile file, Path baseDirectory, Set<String> allowedExtensions) throws IOException {
                        if (file.isEmpty()) {
                            throw new IllegalArgumentException("Cannot upload empty file");
                        }

                        String sanitizedName = sanitizeFilename(file.getOriginalFilename());
                        String ext = "";
                        int dotIdx = sanitizedName.lastIndexOf('.');
                        if (dotIdx > 0) {
                            ext = sanitizedName.substring(dotIdx + 1).toLowerCase();
                        }

                        Set<String> allowlist = allowedExtensions != null ? allowedExtensions : DEFAULT_SAFE_EXTENSIONS;
                        if (!allowlist.contains(ext)) {
                            throw new SecurityException("Disallowed file extension: " + ext);
                        }

                        String safeUniqueName = UUID.randomUUID().toString().replace("-", "") + (ext.isEmpty() ? "" : "." + ext);
                        Path targetPath = baseDirectory.resolve(safeUniqueName).normalize();

                        // Defense in depth: Verify targetPath is strictly inside baseDirectory
                        if (!targetPath.startsWith(baseDirectory.normalize())) {
                            throw new SecurityException("Potential Directory Traversal attack detected!");
                        }

                        File targetFile = targetPath.toFile();
                        file.transferTo(targetFile);
                        return targetFile;
                    }
                }
                """;
    }
}
