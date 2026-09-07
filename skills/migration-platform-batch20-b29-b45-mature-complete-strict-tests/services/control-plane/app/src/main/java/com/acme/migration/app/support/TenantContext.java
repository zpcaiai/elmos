package com.acme.migration.app.support;

import java.util.UUID;

public final class TenantContext {
    public static final UUID LOCAL_TENANT_ID = UUID.fromString("00000000-0000-0000-0000-000000000001");
    private TenantContext() {}
}
