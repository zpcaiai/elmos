package io.elmos.cas;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;

/**
 * ELMOS-CAS-002. An immutable manifest: the addressable statement of "these exact objects, in
 * this exact shape, produced by this exact thing".
 *
 * <p>A manifest is itself content addressed, which is what lets a workflow, an evidence pack and
 * a release all reference the same byte set by one digest, and what lets the collector treat
 * that one reference as a root for the whole graph underneath it.
 *
 * <p>The declared {@code kind} separates an input manifest (what an action was given) from an
 * output manifest (what it produced). They are never interchangeable: an output manifest that
 * could be substituted for an input manifest is a cache-poisoning primitive.
 */
public record CasManifest(String schemaVersion,
                          Kind kind,
                          String tenantId,
                          String projectId,
                          CasDigest rootTreeDigest,
                          List<CasDigest> referencedBlobs,
                          Map<String, String> attributes,
                          Optional<CasDigest> provenanceDigest) {

    public static final String SCHEMA_VERSION = "1.0";
    public static final String FORMAT = "elmos-manifest/1";

    public enum Kind {
        INPUT_ROOT,
        OUTPUT,
        TOOLCHAIN,
        EVIDENCE
    }

    public CasManifest {
        schemaVersion = CasText.required(schemaVersion, "schemaVersion");
        Objects.requireNonNull(kind, "kind");
        tenantId = CasText.required(tenantId, "tenantId");
        projectId = CasText.required(projectId, "projectId");
        Objects.requireNonNull(rootTreeDigest, "rootTreeDigest");
        List<CasDigest> sorted = new ArrayList<>(Objects.requireNonNull(referencedBlobs, "referencedBlobs"));
        sorted.sort(CasDigest::compareTo);
        for (int index = 1; index < sorted.size(); index++) {
            if (sorted.get(index).equals(sorted.get(index - 1))) {
                throw new IllegalArgumentException("duplicate blob reference: " + sorted.get(index));
            }
        }
        referencedBlobs = List.copyOf(sorted);
        attributes = Map.copyOf(new TreeMap<>(Objects.requireNonNull(attributes, "attributes")));
        Objects.requireNonNull(provenanceDigest, "provenanceDigest");
    }

    public static CasManifest output(String tenantId, String projectId, MerkleTree.CanonicalTree tree,
                                     List<CasDigest> blobs) {
        return new CasManifest(SCHEMA_VERSION, Kind.OUTPUT, tenantId, projectId, tree.rootDigest(), blobs,
                Map.of("file_count", Integer.toString(tree.fileCount()),
                        "total_file_bytes", Long.toString(tree.totalFileBytes())),
                Optional.empty());
    }

    /**
     * Canonical bytes. Field order is fixed by this method, not by a map iteration order, and
     * every variable-length value is length prefixed so that no value can impersonate a field
     * boundary.
     */
    public byte[] canonicalBytes() {
        CanonicalEncoder encoder = new CanonicalEncoder(FORMAT);
        encoder.field("schema_version", schemaVersion);
        encoder.field("kind", kind.name());
        encoder.field("tenant_id", tenantId);
        encoder.field("project_id", projectId);
        encoder.field("root_tree_digest", rootTreeDigest.compact());
        encoder.list("referenced_blobs", referencedBlobs.stream().map(CasDigest::compact).toList());
        encoder.map("attributes", attributes);
        encoder.field("provenance_digest", provenanceDigest.map(CasDigest::compact).orElse(""));
        return encoder.bytes();
    }

    public CasDigest digest() {
        return CasDigest.of(canonicalBytes());
    }

    /** Every object this manifest keeps alive, for the collector's mark phase. */
    public List<CasDigest> directReferences() {
        List<CasDigest> references = new ArrayList<>();
        references.add(rootTreeDigest);
        references.addAll(referencedBlobs);
        provenanceDigest.ifPresent(references::add);
        return List.copyOf(references);
    }

    public String toJson() {
        StringBuilder json = new StringBuilder("{");
        json.append("\"schema_version\":\"").append(schemaVersion).append("\",");
        json.append("\"kind\":\"").append(kind).append("\",");
        json.append("\"tenant_id\":").append(CanonicalEncoder.jsonString(tenantId)).append(',');
        json.append("\"project_id\":").append(CanonicalEncoder.jsonString(projectId)).append(',');
        json.append("\"root_tree_digest\":").append(digestJson(rootTreeDigest)).append(',');
        json.append("\"referenced_blobs\":[");
        for (int index = 0; index < referencedBlobs.size(); index++) {
            if (index > 0) {
                json.append(',');
            }
            json.append(digestJson(referencedBlobs.get(index)));
        }
        json.append("],\"attributes\":{");
        boolean first = true;
        for (Map.Entry<String, String> attribute : attributes.entrySet()) {
            if (!first) {
                json.append(',');
            }
            first = false;
            json.append(CanonicalEncoder.jsonString(attribute.getKey())).append(':')
                    .append(CanonicalEncoder.jsonString(attribute.getValue()));
        }
        json.append('}');
        provenanceDigest.ifPresent(digest -> json.append(",\"provenance_digest\":").append(digestJson(digest)));
        return json.append('}').toString();
    }

    private static String digestJson(CasDigest digest) {
        return "{\"algorithm\":\"" + digest.algorithm() + "\",\"hex\":\"" + digest.hex()
                + "\",\"size_bytes\":" + digest.sizeBytes() + "}";
    }

    /**
     * Length-prefixed canonical encoder shared by manifests and action keys.
     *
     * <p>The prefix is the point. A naive {@code join("|", parts)} encoding lets an attacker who
     * controls one field spell out a separator and shift every later field, so two different
     * inputs collapse to one key. With {@code <len>:<bytes>} there is exactly one parse.
     */
    static final class CanonicalEncoder {
        private final StringBuilder buffer;

        CanonicalEncoder(String format) {
            this.buffer = new StringBuilder();
            append(format);
        }

        CanonicalEncoder field(String name, String value) {
            append(name);
            append(value == null ? "" : value);
            return this;
        }

        CanonicalEncoder list(String name, List<String> values) {
            append(name);
            append(Integer.toString(values.size()));
            values.forEach(this::append);
            return this;
        }

        CanonicalEncoder map(String name, Map<String, String> values) {
            Map<String, String> sorted = new TreeMap<>(MerkleTree::compareUtf8);
            sorted.putAll(values);
            append(name);
            append(Integer.toString(sorted.size()));
            sorted.forEach((key, value) -> {
                append(key);
                append(value);
            });
            return this;
        }

        private void append(String value) {
            byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
            buffer.append(bytes.length).append(':').append(value).append('\n');
        }

        byte[] bytes() {
            return buffer.toString().getBytes(StandardCharsets.UTF_8);
        }

        static String jsonString(String value) {
            StringBuilder escaped = new StringBuilder("\"");
            for (int index = 0; index < value.length(); index++) {
                char character = value.charAt(index);
                switch (character) {
                    case '"' -> escaped.append("\\\"");
                    case '\\' -> escaped.append("\\\\");
                    case '\n' -> escaped.append("\\n");
                    case '\r' -> escaped.append("\\r");
                    case '\t' -> escaped.append("\\t");
                    default -> {
                        if (character < 0x20) {
                            escaped.append(String.format("\\u%04x", (int) character));
                        } else {
                            escaped.append(character);
                        }
                    }
                }
            }
            return escaped.append('"').toString();
        }
    }
}
