package io.elmos.cas;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Pattern;

/**
 * Builds a canonical {@link ActionKey}.
 *
 * <p>Two rules do most of the work here, and both exist because of a specific way caches go
 * wrong in production:
 *
 * <ol>
 *   <li><b>Every value is length prefixed</b> before hashing (ELMOS-CAS-022). Joining fields with
 *       a separator lets any attacker-influenced field - a branch name, a label, an argument -
 *       spell out that separator and make two genuinely different actions share one key. That is
 *       a cache-poisoning primitive, not a formatting preference.</li>
 *   <li><b>Undeclared environment variables are an error, not an omission</b>. If an environment
 *       variable can change the output but is not in the key, the cache will confidently serve
 *       the wrong result forever. Refusing to build the key is the only safe response; the caller
 *       must either declare the variable as significant or declare that it is ignored.</li>
 * </ol>
 */
public final class ActionKeyBuilder {

    /** ELMOS-CAS-021. {@code repo/image@sha256:...}; a mutable tag is refused. */
    private static final Pattern PINNED_IMAGE = Pattern.compile("^[^\\s@]+@sha256:[0-9a-f]{64}$");

    /**
     * Canonical schema for every key emitted by this builder.
     *
     * <p>Version 2 fixes the component order independently of fluent-method invocation order. A
     * digest produced with the legacy v1 domain is intentionally not a v2 key, even when its
     * component values happen to use the newer collision-safe composite encodings.</p>
     */
    public static final String CANONICAL_SCHEMA = "elmos-action-key/2";

    /**
     * Schema-owned component order. Optional components are omitted in place; present components
     * are never ordered by caller insertion order or by a platform-dependent map implementation.
     */
    public static final List<String> CANONICAL_COMPONENT_ORDER = List.of(
            "tenant_id", "project_id", "source_tree", "dependency_graph", "adapter",
            "ir_schema_version", "rule_packs", "toolchain_image", "target_platform",
            "build_options", "command", "working_directory", "declared_outputs", "prompt",
            "model", "policy", "permission_scope", "sandbox", "data_residency", "environment");

    /** Component names accepted by the v2 schema. */
    public static final Set<String> CANONICAL_COMPONENT_NAMES =
            Set.copyOf(CANONICAL_COMPONENT_ORDER);

    /** Components without which the action material is incomplete and cannot be cached. */
    public static final List<String> REQUIRED_COMPONENTS = List.of(
            "tenant_id", "project_id", "source_tree", "toolchain_image", "command", "policy",
            "permission_scope", "environment", "declared_outputs", "data_residency");

    /** Digests supplied directly by callers; the referenced content may legitimately be empty. */
    private static final Set<String> DIRECT_DIGEST_COMPONENTS = Set.of(
            "source_tree", "dependency_graph", "policy");

    /**
     * Digests of canonical encodings produced inside this builder. Even an empty canonical list or
     * map has a non-empty encoded representation, so a {@code /0} digest cannot have been emitted
     * by these builder paths.
     */
    private static final Set<String> STRUCTURED_DIGEST_COMPONENTS = Set.of(
            "adapter", "rule_packs", "build_options", "command", "declared_outputs",
            "permission_scope", "sandbox", "environment");

    /** Optional direct digest components use the empty string to bind explicit absence. */
    private static final Set<String> OPTIONAL_DIRECT_DIGEST_COMPONENTS = Set.of("prompt");

    /** Optional builder-encoded digest components use the empty string to bind absence. */
    private static final Set<String> OPTIONAL_STRUCTURED_DIGEST_COMPONENTS = Set.of("model");

    /** {@link #command(List)} refuses this otherwise-valid canonical empty-list encoding. */
    private static final String CANONICAL_EMPTY_LIST_DIGEST = canonicalList(List.of());

    public record ModelIdentity(String provider, String model, String version, Map<String, String> decodingParams) {
        public ModelIdentity {
            provider = CasText.required(provider, "provider");
            model = CasText.required(model, "model");
            version = CasText.required(version, "version");
            decodingParams = Map.copyOf(new TreeMap<>(decodingParams));
        }

        String canonical() {
            CasManifest.CanonicalEncoder encoder =
                    new CasManifest.CanonicalEncoder("elmos-action-model/2");
            encoder.field("provider", provider);
            encoder.field("model", model);
            encoder.field("version", version);
            encoder.map("decoding_params", decodingParams);
            return CasDigest.of(encoder.bytes()).compact();
        }
    }

    public record RulePackRef(String id, CasDigest digest) {
        public RulePackRef {
            id = CasText.required(id, "id");
            Objects.requireNonNull(digest, "digest");
        }

        String canonical() {
            CasManifest.CanonicalEncoder encoder =
                    new CasManifest.CanonicalEncoder("elmos-action-rule-pack/2");
            encoder.field("id", id);
            encoder.field("digest", digest.compact());
            return CasDigest.of(encoder.bytes()).compact();
        }
    }

    /**
     * @param significant environment variables that participate in the key
     * @param ignored     environment variables that provably cannot change the output (a trace id,
     *                    a terminal width). Being explicit here is the point: the set is reviewable.
     */
    public record EnvironmentContract(Set<String> significant, Set<String> ignored) {
        public EnvironmentContract {
            significant = Set.copyOf(significant);
            ignored = Set.copyOf(ignored);
            Set<String> overlap = new TreeSet<>(significant);
            overlap.retainAll(ignored);
            if (!overlap.isEmpty()) {
                throw new IllegalArgumentException("environment variables declared both significant and ignored: " + overlap);
            }
        }

        public static EnvironmentContract of(String... significant) {
            return new EnvironmentContract(Set.of(significant), Set.of());
        }
    }

    /** POLICY failure: an input that can change the output is not covered by the key. */
    public static final class UndeclaredEnvironmentException extends RuntimeException {
        private final List<String> variables;

        UndeclaredEnvironmentException(List<String> variables) {
            super("environment variables are neither significant nor ignored, so the action key cannot "
                    + "cover them: " + variables);
            this.variables = List.copyOf(variables);
        }

        public List<String> variables() {
            return variables;
        }
    }

    private final Map<String, String> components = new LinkedHashMap<>();
    private String tenantId;
    private EnvironmentContract environmentContract = new EnvironmentContract(Set.of(), Set.of());

    public ActionKeyBuilder tenant(String tenantId, String projectId) {
        this.tenantId = CasText.required(tenantId, "tenantId");
        components.put("tenant_id", tenantId);
        components.put("project_id", CasText.required(projectId, "projectId"));
        return this;
    }

    public ActionKeyBuilder sourceTree(CasDigest rootTreeDigest) {
        components.put("source_tree", rootTreeDigest.compact());
        return this;
    }

    public ActionKeyBuilder dependencyGraph(CasDigest digest) {
        components.put("dependency_graph", digest.compact());
        return this;
    }

    public ActionKeyBuilder adapter(String adapterId, CasDigest digest) {
        components.put("adapter", canonicalTuple(
                "elmos-action-adapter/2",
                "id", CasText.required(adapterId, "adapterId"),
                "digest", Objects.requireNonNull(digest, "digest").compact()));
        return this;
    }

    public ActionKeyBuilder irSchemaVersion(String version) {
        components.put("ir_schema_version", CasText.required(version, "irSchemaVersion"));
        return this;
    }

    public ActionKeyBuilder rulePacks(List<RulePackRef> packs) {
        List<String> canonical = new ArrayList<>(packs.stream().map(RulePackRef::canonical).toList());
        canonical.sort(MerkleTree::compareUtf8);
        components.put("rule_packs", canonicalList(canonical));
        return this;
    }

    /** @throws IllegalArgumentException when the reference is a mutable tag rather than a digest */
    public ActionKeyBuilder toolchainImage(String pinnedReference) {
        CasText.required(pinnedReference, "toolchainImage");
        if (!PINNED_IMAGE.matcher(pinnedReference).matches()) {
            throw new IllegalArgumentException("toolchain image must be pinned by digest, not by tag: "
                    + pinnedReference);
        }
        components.put("toolchain_image", pinnedReference);
        return this;
    }

    public ActionKeyBuilder targetPlatform(String platform) {
        components.put("target_platform", CasText.required(platform, "targetPlatform"));
        return this;
    }

    public ActionKeyBuilder buildOptions(Map<String, String> options) {
        components.put("build_options", canonicalMap(options));
        return this;
    }

    public ActionKeyBuilder command(List<String> command) {
        CasText.requireNonEmpty(command, "command");
        components.put("command", canonicalList(command));
        return this;
    }

    public ActionKeyBuilder workingDirectory(String workingDirectory) {
        components.put("working_directory", CasText.required(workingDirectory, "workingDirectory"));
        return this;
    }

    /** Sorted: the declared output set is a set, and its iteration order must not change the key. */
    public ActionKeyBuilder declaredOutputs(List<String> outputs) {
        List<String> sorted = new ArrayList<>(outputs);
        sorted.sort(MerkleTree::compareUtf8);
        components.put("declared_outputs", canonicalList(sorted));
        return this;
    }

    public ActionKeyBuilder prompt(Optional<CasDigest> promptDigest) {
        components.put("prompt", promptDigest.map(CasDigest::compact).orElse(""));
        return this;
    }

    public ActionKeyBuilder model(Optional<ModelIdentity> model) {
        components.put("model", model.map(ModelIdentity::canonical).orElse(""));
        return this;
    }

    public ActionKeyBuilder policy(CasDigest policyDigest) {
        components.put("policy", policyDigest.compact());
        return this;
    }

    /** The scope the action ran under. A different scope is a different action, not a variant. */
    public ActionKeyBuilder permissionScope(Set<String> scope) {
        components.put("permission_scope", canonicalList(new ArrayList<>(new TreeSet<>(scope))));
        return this;
    }

    public ActionKeyBuilder sandbox(String tier, CasDigest sandboxPolicyDigest) {
        components.put("sandbox", canonicalTuple(
                "elmos-action-sandbox/2",
                "tier", CasText.required(tier, "tier"),
                "policy_digest", Objects.requireNonNull(
                        sandboxPolicyDigest, "sandboxPolicyDigest").compact()));
        return this;
    }

    public ActionKeyBuilder dataResidency(String residency) {
        components.put("data_residency", CasText.required(residency, "dataResidency"));
        return this;
    }

    public ActionKeyBuilder environmentContract(EnvironmentContract contract) {
        this.environmentContract = contract;
        return this;
    }

    public ActionKeyBuilder environment(Map<String, String> environment) {
        List<String> undeclared = new ArrayList<>();
        Map<String, String> significant = new TreeMap<>(MerkleTree::compareUtf8);
        for (Map.Entry<String, String> variable : new TreeMap<>(environment).entrySet()) {
            if (environmentContract.significant().contains(variable.getKey())) {
                significant.put(variable.getKey(), variable.getValue());
            } else if (!environmentContract.ignored().contains(variable.getKey())) {
                undeclared.add(variable.getKey());
            }
        }
        if (!undeclared.isEmpty()) {
            throw new UndeclaredEnvironmentException(undeclared);
        }
        components.put("environment", canonicalMap(significant));
        return this;
    }

    public ActionKey build() {
        CasText.required(tenantId, "tenantId");
        List<String> missing = missingRequiredComponents(components);
        if (!missing.isEmpty()) {
            throw new IllegalStateException("action key is missing required components: " + missing);
        }
        Map<String, String> canonicalComponents = canonicalComponents(components);
        ActionKey key = new ActionKey(
                canonicalDigest(canonicalComponents), tenantId, canonicalComponents);
        verifyCanonical(key);
        return key;
    }

    /**
     * Verifies the canonical v2 shape and all builder invariants recognizable without digest
     * preimages: the component set is allowlisted and complete, map iteration order is the schema
     * order, tenant identity is bound twice, and the digest is recomputed under the v2 domain.
     * Component validation distinguishes caller-supplied digests from builder-encoded digests and
     * rejects invalid shapes plus known-impossible canonical encodings. Structured component
     * digests are intentionally opaque: verification cannot prove an arbitrary SHA-256 preimage,
     * so this method does not claim to reconstruct their original lists, maps, or tuples. There is
     * intentionally no legacy-v1 fallback.
     *
     * @throws IllegalArgumentException when a canonical shape or recognizable builder invariant
     *                                  is absent or forged
     */
    public static void verifyCanonical(ActionKey key) {
        Objects.requireNonNull(key, "key");
        Map<String, String> components = key.components();
        List<String> missing = missingRequiredComponents(components);
        if (!missing.isEmpty()
                || components.size() > CANONICAL_COMPONENT_NAMES.size()
                || !CANONICAL_COMPONENT_NAMES.containsAll(components.keySet())
                || !key.tenantId().equals(components.get("tenant_id"))) {
            throw new IllegalArgumentException("ActionKey component set is not canonical v2");
        }
        components.forEach((name, value) -> {
            if (name == null || value == null) {
                throw new IllegalArgumentException(
                        "ActionKey canonical v2 components cannot be null");
            }
        });
        validateComponentSemantics(components);
        Map<String, String> canonicalComponents = canonicalComponents(components);
        if (!List.copyOf(components.keySet())
                .equals(List.copyOf(canonicalComponents.keySet()))) {
            throw new IllegalArgumentException("ActionKey components are not in canonical v2 order");
        }
        if (!canonicalDigest(canonicalComponents).equals(key.digest())) {
            throw new IllegalArgumentException("ActionKey digest does not bind canonical v2 components");
        }
    }

    private static List<String> missingRequiredComponents(Map<String, String> candidate) {
        List<String> missing = new ArrayList<>();
        for (String required : REQUIRED_COMPONENTS) {
            if (!candidate.containsKey(required)) {
                missing.add(required);
            }
        }
        return List.copyOf(missing);
    }

    private static Map<String, String> canonicalComponents(Map<String, String> candidate) {
        Map<String, String> canonical = new LinkedHashMap<>();
        for (String component : CANONICAL_COMPONENT_ORDER) {
            if (candidate.containsKey(component)) {
                canonical.put(component, candidate.get(component));
            }
        }
        if (canonical.size() != candidate.size()) {
            throw new IllegalArgumentException("ActionKey contains a component outside the v2 schema");
        }
        return canonical;
    }

    private static void validateComponentSemantics(Map<String, String> components) {
        for (Map.Entry<String, String> component : components.entrySet()) {
            String name = component.getKey();
            String value = component.getValue();
            if (DIRECT_DIGEST_COMPONENTS.contains(name)) {
                CasDigest.parseCompact(value);
                continue;
            }
            if (STRUCTURED_DIGEST_COMPONENTS.contains(name)) {
                requireBuilderEncodedDigest(name, value);
                if ("command".equals(name) && CANONICAL_EMPTY_LIST_DIGEST.equals(value)) {
                    throw new IllegalArgumentException(
                            "ActionKey command cannot be the canonical empty-list encoding");
                }
                continue;
            }
            if (OPTIONAL_DIRECT_DIGEST_COMPONENTS.contains(name)) {
                if (!value.isEmpty()) {
                    CasDigest.parseCompact(value);
                }
                continue;
            }
            if (OPTIONAL_STRUCTURED_DIGEST_COMPONENTS.contains(name)) {
                if (!value.isEmpty()) {
                    requireBuilderEncodedDigest(name, value);
                }
                continue;
            }
            CasText.required(value, "ActionKey component " + name);
            if ("toolchain_image".equals(name) && !PINNED_IMAGE.matcher(value).matches()) {
                throw new IllegalArgumentException(
                        "ActionKey toolchain_image is not pinned by sha256 digest");
            }
        }
    }

    private static void requireBuilderEncodedDigest(String name, String value) {
        CasDigest digest = CasDigest.parseCompact(value);
        if (digest.sizeBytes() == 0) {
            throw new IllegalArgumentException(
                    "ActionKey builder-encoded component " + name
                            + " cannot have an empty canonical encoding");
        }
    }

    private static CasDigest canonicalDigest(Map<String, String> canonicalComponents) {
        CasManifest.CanonicalEncoder encoder = new CasManifest.CanonicalEncoder(CANONICAL_SCHEMA);
        canonicalComponents.forEach(encoder::field);
        return CasDigest.of(encoder.bytes());
    }

    private static String canonicalList(List<String> values) {
        CasManifest.CanonicalEncoder encoder = new CasManifest.CanonicalEncoder("list/1");
        encoder.list("items", values);
        return CasDigest.of(encoder.bytes()).compact();
    }

    private static String canonicalMap(Map<String, String> values) {
        CasManifest.CanonicalEncoder encoder = new CasManifest.CanonicalEncoder("map/1");
        encoder.map("entries", values);
        return CasDigest.of(encoder.bytes()).compact();
    }

    private static String canonicalTuple(String format, String... namesAndValues) {
        if (namesAndValues.length == 0 || namesAndValues.length % 2 != 0) {
            throw new IllegalArgumentException("canonical tuple requires name/value pairs");
        }
        CasManifest.CanonicalEncoder encoder = new CasManifest.CanonicalEncoder(format);
        for (int index = 0; index < namesAndValues.length; index += 2) {
            encoder.field(namesAndValues[index], namesAndValues[index + 1]);
        }
        return CasDigest.of(encoder.bytes()).compact();
    }
}
