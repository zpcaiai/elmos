package io.elmos.cas;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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

    public record ModelIdentity(String provider, String model, String version, Map<String, String> decodingParams) {
        public ModelIdentity {
            provider = CasText.required(provider, "provider");
            model = CasText.required(model, "model");
            version = CasText.required(version, "version");
            decodingParams = Map.copyOf(new TreeMap<>(decodingParams));
        }

        String canonical() {
            StringBuilder text = new StringBuilder(provider).append('/').append(model).append('@').append(version);
            decodingParams.forEach((key, value) -> text.append(';').append(key).append('=').append(value));
            return text.toString();
        }
    }

    public record RulePackRef(String id, CasDigest digest) {
        public RulePackRef {
            id = CasText.required(id, "id");
        }

        String canonical() {
            return id + "=" + digest.compact();
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
        components.put("adapter", CasText.required(adapterId, "adapterId") + "=" + digest.compact());
        return this;
    }

    public ActionKeyBuilder irSchemaVersion(String version) {
        components.put("ir_schema_version", CasText.required(version, "irSchemaVersion"));
        return this;
    }

    public ActionKeyBuilder rulePacks(List<RulePackRef> packs) {
        List<String> canonical = new ArrayList<>(packs.stream().map(RulePackRef::canonical).toList());
        canonical.sort(MerkleTree::compareUtf8);
        components.put("rule_packs", String.join(",", canonical));
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
        components.put("sandbox", CasText.required(tier, "tier") + "=" + sandboxPolicyDigest.compact());
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
        List<String> missing = new ArrayList<>();
        for (String required : List.of("source_tree", "toolchain_image", "command", "policy",
                "permission_scope", "environment", "declared_outputs", "data_residency")) {
            if (!components.containsKey(required)) {
                missing.add(required);
            }
        }
        if (!missing.isEmpty()) {
            throw new IllegalStateException("action key is missing required components: " + missing);
        }
        CasManifest.CanonicalEncoder encoder = new CasManifest.CanonicalEncoder("elmos-action-key/1");
        components.forEach(encoder::field);
        return new ActionKey(CasDigest.of(encoder.bytes()), tenantId, components);
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
}
