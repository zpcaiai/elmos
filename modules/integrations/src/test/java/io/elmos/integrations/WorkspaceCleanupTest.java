package io.elmos.integrations;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.concurrent.RejectedExecutionException;
import static org.junit.jupiter.api.Assertions.*;

class WorkspaceCleanupTest {
    @TempDir Path root;

    @Test void boundsOutstandingWorkAndCoalescesSameIdentity() {
        var reservations = new ArrayList<WorkspaceCleanup.Reservation>();
        try {
            for (int i = 0; i < 32; i++) {
                var reservation = WorkspaceCleanup.reserve(root.resolve("work-" + i));
                assertNotNull(reservation);
                reservations.add(reservation);
            }
            assertNull(WorkspaceCleanup.reserve(root.resolve("overflow")));
            assertNull(WorkspaceCleanup.reserve(root.resolve("work-0")));
        } finally { reservations.forEach(WorkspaceCleanup.Reservation::close); }
        try (var available = WorkspaceCleanup.reserve(root.resolve("overflow"))) {
            assertNotNull(available);
        }
    }

    @Test void capacityRemainsReservedUntilActualCleanupExit() {
        var pending = new ArrayList<Runnable>();
        var key = root.resolve("pending");
        try (var reservation = WorkspaceCleanup.reserve(key)) {
            assertNotNull(reservation);
            reservation.submit(pending::add, () -> { throw new IllegalStateException("retry"); });
        }
        assertNull(WorkspaceCleanup.reserve(key));
        pending.removeFirst().run();
        try (var again = WorkspaceCleanup.reserve(key)) { assertNotNull(again); }
    }

    @Test void rejectionReleasesReservationWithoutRunningWorkInline() {
        var key = root.resolve("rejected");
        try (var reservation = WorkspaceCleanup.reserve(key)) {
            reservation.submit(task -> { throw new RejectedExecutionException(); },
                    () -> fail("cleanup must never run inline after rejection"));
        }
        try (var again = WorkspaceCleanup.reserve(key)) { assertNotNull(again); }
    }
}
