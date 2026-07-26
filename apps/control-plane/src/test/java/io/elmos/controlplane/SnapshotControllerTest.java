package io.elmos.controlplane;

import io.elmos.persistence.JdbcGitHubRepositoryCatalog;
import io.elmos.snapshot.SnapshotCaptureService;
import io.elmos.snapshot.SnapshotMaterializationService;
import io.elmos.snapshot.SnapshotModel;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SnapshotControllerTest {
    @Test void derivesOrganizationFromTrustedHeaderAndRejectsBodySpoofing() {
        SnapshotCaptureService service = mock(SnapshotCaptureService.class);
        SnapshotModel.RepositorySnapshot snapshot = new SnapshotModel.RepositorySnapshot(
                "snapshot-1", "org-a", "repo-1", "main", "a".repeat(40),
                "b".repeat(40), "cas:sha256:" + "c".repeat(64), "c".repeat(64),
                10, "cas:sha256:" + "d".repeat(64), "d".repeat(64), 1,
                SnapshotModel.Status.AVAILABLE, Instant.parse("2026-07-26T00:00:00Z"));
        when(service.capture(any())).thenReturn(snapshot);
        SnapshotController controller = new SnapshotController(
                service,
                mock(SnapshotMaterializationService.class),
                mock(JdbcGitHubRepositoryCatalog.class));
        var request = new SnapshotController.CaptureRequest(
                null, "repo-1", 11, 22, "example/repo", "main",
                "correlation-1", "idempotency-1");

        assertEquals(snapshot, controller.capture("org-a", request));
        verify(service).capture(new SnapshotCaptureService.CaptureRequest(
                "org-a", "repo-1", 11, 22, "example/repo", "main",
                "correlation-1", "idempotency-1"));

        var spoofed = new SnapshotController.CaptureRequest(
                "org-b", "repo-1", 11, 22, "example/repo", "main",
                "correlation-2", "idempotency-2");
        assertThrows(SecurityException.class,
                () -> controller.capture("org-a", spoofed));
    }
}
