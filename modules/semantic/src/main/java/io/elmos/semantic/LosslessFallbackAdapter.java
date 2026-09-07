package io.elmos.semantic;

import io.elmos.intake.IntakeModels.FileEntry;

import java.nio.file.Files;
import java.time.Instant;
import java.util.*;

import static io.elmos.semantic.PspModels.*;

/** Error-tolerant token/CST fallback. It deliberately emits no authoritative binding or type claim. */
public final class LosslessFallbackAdapter implements SemanticAdapter {
    private static final Set<String> SUPPORTED = Set.of("java", "python", "csharp", "javascript", "typescript");
    private final AdapterDescriptor descriptor;

    public LosslessFallbackAdapter(String language) {
        if (!SUPPORTED.contains(language)) throw new IllegalArgumentException("unsupported fallback language");
        descriptor = new AdapterDescriptor(language + "-semantic-fallback", "1.0.0", language,
                "elmos-lossless-tokenizer", "1.0.0", false, true, SemanticIds.hashText("fallback:" + language));
    }
    @Override public AdapterDescriptor descriptor() { return descriptor; }

    @Override public AdapterResult analyze(AdapterRequest request) {
        List<EntityEnvelope> entities = new ArrayList<>(); List<String> invalidation = new ArrayList<>(); boolean partial = false;
        for (FileEntry file : request.files().stream().filter(value -> language(value.path()).equals(descriptor.language())).sorted(Comparator.comparing(FileEntry::path)).toList()) {
            if (file.generated() || file.vendored() || file.binary() || file.secretLike()) continue;
            try { analyzeFile(request, file, entities); invalidation.add(file.sha256()); }
            catch (RuntimeException | java.io.IOException error) { entities.add(diagnostic(request, file, "parse-recovery", "error", error.getMessage(), "fallback-parse-failed", true)); partial = true; }
        }
        if (!descriptor.authoritativeSemantics()) {
            String fileId = request.files().stream().filter(file -> language(file.path()).equals(descriptor.language())).findFirst()
                    .map(file -> SemanticIds.file(request.snapshotId(), file.path())).orElse("file:none");
            String id = SemanticIds.diagnostic(descriptor.provider(), "binding-failure", fileId, 0, "AUTHORITATIVE_PROVIDER_UNAVAILABLE");
            DiagnosticPayload payload = new DiagnosticPayload(id, "binding-failure", "blocking", fileId, null,
                    "Authoritative semantic provider is unavailable; fallback syntax is not sufficient for Batch 3",
                    descriptor.provider(), "AUTHORITATIVE_PROVIDER_UNAVAILABLE", List.of("symbol-resolution-incomplete", "type-resolution-incomplete", "call-graph-incomplete"),
                    "configure-authoritative-adapter", 1.0, true);
            entities.add(envelope(request, "diagnostic", id, payload, "fallback-provider-gate", "unresolved", 1.0));
        }
        return new AdapterResult(descriptor, entities, invalidation.stream().sorted().toList(), partial);
    }

    private void analyzeFile(AdapterRequest request, FileEntry file, List<EntityEnvelope> entities) throws java.io.IOException {
        byte[] bytes = Files.readAllBytes(request.repositoryRoot().resolve(file.path())); String fileId = SemanticIds.file(request.snapshotId(), file.path());
        SourceText source = SourceText.utf8(fileId, bytes); List<SourceText.Span> spans = source.lex(descriptor.language());
        FilePayload filePayload = new FilePayload(fileId, request.project().projectId(), file.path(), descriptor.language(), "sha256:" + file.sha256(),
                bytes.length, "UTF-8", source.lineEnding(), file.category().name().toLowerCase(Locale.ROOT).replace('_','-'), file.generated(), file.category().name().equals("TEST_SOURCE"), "tree-sitter-compatible-fallback", true);
        entities.add(envelope(request, "file", fileId, filePayload, "metadata", "exact", 1.0));
        String rootNode = SemanticIds.node(request.snapshotId(), file.path(), descriptor.provider(), "source-file", 0, bytes.length);
        List<String> tokenIds = new ArrayList<>(), commentIds = new ArrayList<>(); int sequence = 0;
        for (SourceText.Span span : spans) {
            SourceRange range = source.range(span.startChar(), span.endChar());
            if (span.comment()) {
                String id = SemanticIds.id("comment", fileId, range.startByte(), range.endByte(), sequence++); commentIds.add(id);
                entities.add(envelope(request, "comment", id, new CommentPayload(span.commentCategory(), span.textHash(), range, rootNode), "fallback-lexer", "exact", 1.0));
            } else {
                String id = SemanticIds.id("token", fileId, range.startByte(), range.endByte(), sequence++); tokenIds.add(id);
                entities.add(envelope(request, "token", id, new TokenPayload(span.kind(), span.textHash(), range), "fallback-lexer", "exact", 1.0));
            }
        }
        SourceRange whole = source.range(0, source.text().length());
        entities.add(envelope(request, "syntax-node", rootNode, new SyntaxNodePayload(rootNode, "source-file", null, whole, false, tokenIds, commentIds, Map.of("fallback", true)), "fallback-cst", "exact", .8));
        String fileScope = SemanticIds.scope(fileId, "file", 0);
        entities.add(envelope(request, "scope", fileScope, new ScopePayload(fileScope, "file", null, null, whole), "lexical-scope", "exact", .8));
        emitDeclarationsAndRisks(request, file, fileId, fileScope, source, spans, rootNode, entities);
    }

    private void emitDeclarationsAndRisks(AdapterRequest request, FileEntry file, String fileId, String fileScope, SourceText source,
                                          List<SourceText.Span> spans, String rootNode, List<EntityEnvelope> entities) {
        List<SourceText.Span> significant = spans.stream().filter(span -> !span.comment() && !span.kind().equals("whitespace")).toList();
        for (int i = 0; i < significant.size(); i++) {
            SourceText.Span current = significant.get(i); String token = source.text().substring(current.startChar(), current.endChar());
            String declarationKind = declarationKind(descriptor.language(), token, i > 0 ? source.text().substring(significant.get(i - 1).startChar(), significant.get(i - 1).endChar()) : null);
            if (declarationKind != null && i + 1 < significant.size()) {
                SourceText.Span nameSpan = significant.get(i + 1); String name = source.text().substring(nameSpan.startChar(), nameSpan.endChar());
                if (!nameSpan.kind().equals("identifier")) continue;
                SourceRange range = source.range(current.startChar(), nameSpan.endChar()); String node = SemanticIds.node(request.snapshotId(), file.path(), descriptor.provider(), declarationKind, range.startByte(), range.endByte());
                String symbol = SemanticIds.symbol(descriptor.language(), request.project().projectId(), file.path() + ":" + declarationKind + ":" + name + ":" + range.startByte());
                String unknownType = SemanticIds.type(descriptor.language(), "unknown");
                entities.add(envelope(request, "syntax-node", node, new SyntaxNodePayload(node, declarationKind, rootNode, range, false, List.of(), List.of(), Map.of("fallback", true)), "declaration-token-pattern", "name-inferred", .5));
                entities.add(envelope(request, "type", unknownType, new TypePayload(unknownType, "unknown", "Unknown", null, List.of(), List.of(), null, List.of(), "unknown", "unknown", "runtime-unknown", 0, Map.of("fallback", true)), "unknown-type", "unresolved", 0));
                entities.add(envelope(request, "symbol", symbol, new SymbolPayload(symbol, declarationKind, name, file.path() + ":" + name, null, fileScope, "unknown", List.of(),
                        List.of(new DeclarationSite(fileId, node, range)), unknownType, Map.of(), List.of(), false, file.category().name().equals("TEST_SOURCE"), Map.of("fallback", true)), "declaration-token-pattern", "name-inferred", .5));
                String map = SemanticIds.id("smap", node, symbol); entities.add(envelope(request, "source-map", map, new SourceMapPayload(node, symbol, unknownType, null, null, range, List.of()), "fallback-source-map", "exact", 1.0));
            }
            String risk = dynamicRisk(descriptor.language(), token);
            if (risk != null) {
                SourceRange range = source.range(current.startChar(), current.endChar()); String id = SemanticIds.diagnostic(descriptor.provider(), risk, fileId, range.startByte(), token);
                entities.add(envelope(request, "diagnostic", id, new DiagnosticPayload(id, risk, "warning", fileId, range, "Runtime-dependent language feature detected", descriptor.provider(), token,
                        List.of("call-graph-incomplete", "translation-risk"), "runtime-trace", 1.0, false), "dynamic-risk-rule", "dynamic", 1.0));
            }
        }
    }

    private EntityEnvelope diagnostic(AdapterRequest request, FileEntry file, String category, String severity, String message, String code, boolean blocking) {
        String fileId = SemanticIds.file(request.snapshotId(), file.path()), id = SemanticIds.diagnostic(descriptor.provider(), category, fileId, 0, code);
        return envelope(request, "diagnostic", id, new DiagnosticPayload(id, category, severity, fileId, null, message == null ? code : message,
                descriptor.provider(), code, List.of("syntax-incomplete"), "inspect-source", 1.0, blocking), "adapter-error", "unresolved", 1.0);
    }
    private EntityEnvelope envelope(AdapterRequest request, String kind, String id, Object payload, String method, String resolution, double confidence) {
        Provenance provenance = new Provenance(descriptor.adapter(), descriptor.adapterVersion(), descriptor.provider(), descriptor.providerVersion(), method,
                request.profile().name(), resolution, confidence, request.files().stream().map(FileEntry::sha256).sorted().toList(), Instant.EPOCH);
        return new EntityEnvelope(PROTOCOL_VERSION, kind, id, request.snapshotId(), request.semanticRunId(), request.project().projectId(), descriptor.language(), payload, provenance);
    }
    private static String declarationKind(String language, String token, String previous) {
        return switch (language) {
            case "python" -> token.equals("class") ? "class" : token.equals("def") ? "function" : token.equals("async") ? null : null;
            case "java" -> Set.of("class","interface","enum","record").contains(token) ? token : null;
            case "csharp" -> Set.of("class","interface","struct","record","enum","delegate").contains(token) ? token : null;
            case "typescript", "javascript" -> Set.of("class","interface","enum","function","type").contains(token) ? (token.equals("type") ? "type-alias" : token) : null;
            default -> null;
        };
    }
    private static String dynamicRisk(String language, String token) {
        if (language.equals("python") && Set.of("eval","exec","getattr","setattr","__import__").contains(token)) return token.equals("__import__") ? "runtime-code-generation" : "dynamic-call";
        if ((language.equals("javascript") || language.equals("typescript")) && Set.of("eval","Proxy","require","Function").contains(token)) return token.equals("require") ? "runtime-code-generation" : "dynamic-call";
        if (language.equals("java") && Set.of("Class","forName","Proxy").contains(token)) return "reflection";
        if (language.equals("csharp") && Set.of("dynamic","Reflection","Activator").contains(token)) return token.equals("dynamic") ? "dynamic-call" : "reflection";
        return null;
    }
    private static String language(String path) { String lower = path.toLowerCase(Locale.ROOT); if (lower.endsWith(".java")) return "java"; if (lower.endsWith(".py") || lower.endsWith(".pyi")) return "python"; if (lower.endsWith(".cs")) return "csharp"; if (lower.endsWith(".ts") || lower.endsWith(".tsx") || lower.endsWith(".d.ts")) return "typescript"; if (lower.endsWith(".js") || lower.endsWith(".jsx") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) return "javascript"; return "other"; }
}
