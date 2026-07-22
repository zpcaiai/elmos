package io.elmos.infrastructure;

import static io.elmos.infrastructure.InfrastructureModels.MigrationState;

public final class InfrastructureLifecycle {
    public MigrationState advance(MigrationState current, MigrationState requested) {
        if (requested.ordinal() != current.ordinal() + 1) {
            throw new IllegalStateException("INFRASTRUCTURE_STAGE_SKIP");
        }
        return requested;
    }
}
