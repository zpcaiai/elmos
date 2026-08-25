package io.elmos.cas;

import java.util.Objects;

/** Resolves the physical CAS view for an authenticated tenant. */
public interface TenantCasStore {

    enum DeletionScope {
        /** One tenant's physical delete cannot remove another tenant's identical digest. */
        TENANT_ISOLATED,
        /** Identical digests share physical bytes and require a cross-tenant GC authority. */
        GLOBAL_SHARED
    }

    CasStore forTenant(String tenantId);

    String atRestProtection();

    String physicalNamespace();

    /**
     * Destructive GC is fail-closed for a globally shared store unless a separate cross-tenant
     * authority exists. Implementations are global by default so a new store cannot silently opt
     * into tenant-local deletion.
     */
    default DeletionScope deletionScope() {
        return DeletionScope.GLOBAL_SHARED;
    }

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
