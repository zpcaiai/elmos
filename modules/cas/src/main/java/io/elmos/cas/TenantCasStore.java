package io.elmos.cas;

import java.util.Objects;

/** Resolves the physical CAS view for an authenticated tenant. */
public interface TenantCasStore {

    CasStore forTenant(String tenantId);

    String atRestProtection();

    String physicalNamespace();

    static TenantCasStore global(CasStore store) {
        Objects.requireNonNull(store, "store");
        return new TenantCasStore() {
            @Override
            public CasStore forTenant(String tenantId) {
                CasText.required(tenantId, "tenantId");
                return store;
            }

            @Override
            public String atRestProtection() {
                return "NOT_CONFIGURED";
            }

            @Override
            public String physicalNamespace() {
                return "GLOBAL_DIGEST";
            }
        };
    }
}
