package io.elmos.productionruntime;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Exact provider/model registry; there is no generic or fallback provider. */
public final class ProductionModelProviderRegistry {
    private final Map<String, ProductionModelProviderPort> providers;

    public ProductionModelProviderRegistry(
            Map<String, ProductionModelProviderPort> providers
    ) {
        Objects.requireNonNull(providers, "providers");
        Map<String, ProductionModelProviderPort> checked = new LinkedHashMap<>();
        providers.forEach((name, adapter) -> {
            ProductionRuntimeModels.requireText(name, "provider/model key", 320);
            if (!name.contains("\u0000")) {
                throw new IllegalArgumentException("provider registry key must be created with key(provider, model)");
            }
            Objects.requireNonNull(adapter, "provider adapter");
            if (checked.put(name, adapter) != null) {
                throw new IllegalArgumentException("duplicate provider adapter: " + name);
            }
        });
        if (checked.isEmpty()) throw new IllegalArgumentException("at least one provider adapter is required");
        this.providers = Map.copyOf(checked);
    }

    public ProductionModelProviderPort require(String provider, String model) {
        ProductionModelProviderPort adapter = providers.get(key(provider, model));
        if (adapter == null) {
            throw new ProductionRuntimeException(
                    "MODEL_PROVIDER_NOT_CONFIGURED",
                    "no exact provider adapter is configured for " + provider + "/" + model);
        }
        return adapter;
    }

    public List<String> configuredProfiles() {
        return providers.keySet().stream()
                .map(value -> value.replace('\u0000', '/'))
                .sorted().toList();
    }

    public static String key(String provider, String model) {
        ProductionRuntimeModels.requireText(provider, "provider", 80);
        ProductionRuntimeModels.requireText(model, "model", 200);
        return provider + "\u0000" + model;
    }
}
