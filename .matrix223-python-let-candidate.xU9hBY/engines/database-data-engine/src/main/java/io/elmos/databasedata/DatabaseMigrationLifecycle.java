package io.elmos.databasedata;

import java.util.List;

import static io.elmos.databasedata.DatabaseDataModels.MigrationState;

public final class DatabaseMigrationLifecycle {
    private static final List<MigrationState> ORDER = List.of(MigrationState.values());

    public MigrationState advance(MigrationState current, MigrationState requested) {
        int currentIndex = ORDER.indexOf(current);
        if (currentIndex < 0 || currentIndex + 1 >= ORDER.size() || ORDER.get(currentIndex + 1) != requested) {
            throw new IllegalStateException("database migration must advance one governed state: "
                    + current + " -> " + requested);
        }
        return requested;
    }
}
