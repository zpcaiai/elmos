package io.elmos.portfolio;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.portfolio.PortfolioScaleModels.requireText;

public final class TenantSemanticIndex {
    public record SemanticDocument(String tenantId, String documentId, String repositoryId,
                                   String baselineDigest, String symbol, String payloadDigest,
                                   long version, Set<String> readers, boolean tombstone) {
        public SemanticDocument {
            requireText(tenantId, "document tenant");
            requireText(documentId, "document id");
            requireText(repositoryId, "document repository");
            requireText(baselineDigest, "document baseline");
            requireText(symbol, "document symbol");
            requireText(payloadDigest, "document payload digest");
            readers = Set.copyOf(readers);
            if (version < 1 || readers.isEmpty()) throw new IllegalArgumentException("invalid semantic document version or ACL");
        }
    }

    private final Map<String, SemanticDocument> documents = new HashMap<>();

    public void upsert(SemanticDocument document) {
        String key = key(document.tenantId(), document.documentId());
        SemanticDocument prior = documents.get(key);
        if (prior != null && document.version() <= prior.version()) {
            throw new IllegalArgumentException("semantic document version must increase");
        }
        documents.put(key, document);
    }

    public List<SemanticDocument> query(String tenantId, String reader, String baselineDigest, String symbolPrefix) {
        requireText(tenantId, "query tenant");
        requireText(reader, "query reader");
        requireText(baselineDigest, "query baseline");
        String prefix = symbolPrefix == null ? "" : symbolPrefix;
        return documents.values().stream()
                .filter(document -> document.tenantId().equals(tenantId))
                .filter(document -> !document.tombstone())
                .filter(document -> document.readers().contains(reader))
                .filter(document -> document.baselineDigest().equals(baselineDigest))
                .filter(document -> document.symbol().startsWith(prefix))
                .sorted(Comparator.comparing(SemanticDocument::documentId)).toList();
    }

    public String snapshotDigest(String tenantId) {
        List<String> canonical = new ArrayList<>();
        documents.values().stream().filter(document -> document.tenantId().equals(tenantId))
                .sorted(Comparator.comparing(SemanticDocument::documentId)).forEach(document -> canonical.add(String.join("\0",
                        document.documentId(), document.repositoryId(), document.baselineDigest(), document.symbol(),
                        document.payloadDigest(), Long.toString(document.version()), Boolean.toString(document.tombstone()),
                        String.join(",", document.readers().stream().sorted().toList()))));
        return digest(String.join("\n", canonical));
    }

    public static TenantSemanticIndex rebuild(List<SemanticDocument> documents) {
        TenantSemanticIndex index = new TenantSemanticIndex();
        documents.stream().sorted(Comparator.comparingLong(SemanticDocument::version)).forEach(index::upsert);
        return index;
    }

    private static String key(String tenantId, String documentId) { return tenantId + "\0" + documentId; }
    private static String digest(String value) {
        try {
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) { throw new IllegalStateException(error); }
    }
}
