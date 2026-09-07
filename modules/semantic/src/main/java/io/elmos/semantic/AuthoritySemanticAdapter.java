package io.elmos.semantic;

import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static io.elmos.semantic.PspModels.AdapterDescriptor;

/** Routes an allowlisted authoritative analyzer through an isolated execution port. */
public final class AuthoritySemanticAdapter implements SemanticAdapter {
    private static final Map<String, Set<String>> ALLOWED = Map.of(
            "java", Set.of("eclipse-jdt", "javac", "javaparser-symbol-solver", "openrewrite-lst"),
            "python", Set.of("libcst+pyright"),
            "csharp", Set.of("roslyn"),
            "javascript", Set.of("typescript-compiler-api+babel"),
            "typescript", Set.of("typescript-compiler-api+babel"));
    private final AdapterDescriptor descriptor; private final NativeAnalyzerPort port;

    public AuthoritySemanticAdapter(AdapterDescriptor descriptor, NativeAnalyzerPort port) {
        this.descriptor = Objects.requireNonNull(descriptor); this.port = Objects.requireNonNull(port);
        if (!descriptor.authoritativeSemantics()) throw new IllegalArgumentException("authoritative adapter descriptor is required");
        if (!ALLOWED.getOrDefault(descriptor.language(), Set.of()).contains(descriptor.provider()))
            throw new SecurityException("semantic provider is not allowlisted for " + descriptor.language());
    }
    @Override public AdapterDescriptor descriptor() { return descriptor; }
    @Override public AdapterResult analyze(AdapterRequest request) {
        AdapterResult result = Objects.requireNonNull(port.analyze(descriptor, request), "native analyzer result");
        if (!descriptor.equals(result.descriptor())) throw new SecurityException("native analyzer descriptor mismatch");
        return result;
    }
}
