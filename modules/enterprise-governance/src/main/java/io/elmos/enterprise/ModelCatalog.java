package io.elmos.enterprise;

import java.util.List;

/**
 * Java-side mirror of the {@code modelId} values declared in
 * {@code engines/ai-platform-engine/policies/model-catalog-v1.json}.
 *
 * This module intentionally has no JSON dependency (see ADR-0059 discussion:
 * kept minimal rather than pulling a new library into the reactor for one
 * flat list), so the 14 ids are duplicated here as a plain constant instead
 * of being parsed from the JSON at runtime. {@code scripts/operations/validate_model_catalog.py}
 * cross-checks this file against the JSON catalog on every run so the two
 * cannot silently drift.
 */
public final class ModelCatalog {
    private ModelCatalog() {}

    public static final List<String> MODEL_IDS = List.of(
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "claude-fable-5",
            "claude-opus-5",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "grok-4.5",
            "grok-build-0.1",
            "qwen3.8-max-preview",
            "glm-5.2",
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "doubao-seed-2.1",
            "doubao-seed-code"
    );
}
