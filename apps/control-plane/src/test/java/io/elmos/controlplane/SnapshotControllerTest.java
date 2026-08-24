package io.elmos.controlplane;

import io.elmos.persistence.JdbcGitHubRepositoryCatalog;
import io.elmos.snapshot.SnapshotArchiveService;
import io.elmos.snapshot.SnapshotCaptureService;
import io.elmos.snapshot.SnapshotMaterializationService;
import io.elmos.snapshot.SnapshotModel;
import io.elmos.snapshot.SnapshotProvisionalRootReconciler;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.AfterEach;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.time.Instant;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SnapshotControllerTest {
    @AfterEach void resetRequestContext() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test void derivesAllRepositoryIdentityFromTheTenantCatalog() {
        bindPrincipal("org-a", Set.of("repository:read"));
        SnapshotCaptureService service = mock(SnapshotCaptureService.class);
        JdbcGitHubRepositoryCatalog catalog = mock(JdbcGitHubRepositoryCatalog.class);
        SnapshotModel.RepositorySnapshot snapshot = new SnapshotModel.RepositorySnapshot(
                "snapshot-1", "org-a", "repo-1", "main", "a".repeat(40),
                "b".repeat(40), "cas:sha256:" + "c".repeat(64), "c".repeat(64),
                10, "cas:sha256:" + "d".repeat(64), "d".repeat(64), 1,
                SnapshotModel.Status.AVAILABLE, Instant.parse("2026-07-26T00:00:00Z"));
        when(service.capture(any())).thenReturn(snapshot);
        when(catalog.requireAuthorized("org-a", "repo-1")).thenReturn(
                new JdbcGitHubRepositoryCatalog.AuthorizedRepository(
                        "repo-1", 11, 22, "example/repo", "main", "PRIVATE"));
        SnapshotController controller = new SnapshotController(
                service,
                mock(SnapshotMaterializationService.class),
                catalog,
                mock(SnapshotArchiveService.class),
                mock(SnapshotProvisionalRootReconciler.class));
        var request = new SnapshotController.CaptureRequest(
                "repo-1", "", "correlation-1", "idempotency-1");

        assertEquals(snapshot, controller.capture("org-a", request));
        verify(service).capture(new SnapshotCaptureService.CaptureRequest(
                "org-a", "repo-1", 11, 22, "example/repo", "main",
                "correlation-1", "idempotency-1"));

        when(catalog.requireAuthorized("org-a", "foreign-repo"))
                .thenThrow(new SecurityException("repository is not tenant-owned"));
        var spoofed = new SnapshotController.CaptureRequest(
                "foreign-repo", "main", "correlation-2", "idempotency-2");
        assertThrows(SecurityException.class,
                () -> controller.capture("org-a", spoofed));
    }

    @Test void archiveAndReconciliationUseOnlyTheTrustedOrganization() {
        bindPrincipal("org-a", Set.of("repository:write", "admin:operate"));
        SnapshotArchiveService archives = mock(SnapshotArchiveService.class);
        SnapshotProvisionalRootReconciler reconciler =
                mock(SnapshotProvisionalRootReconciler.class);
        SnapshotController controller = new SnapshotController(
                mock(SnapshotCaptureService.class),
                mock(SnapshotMaterializationService.class),
                mock(JdbcGitHubRepositoryCatalog.class), archives, reconciler);
        SnapshotArchiveService.ArchiveResult archived =
                new SnapshotArchiveService.ArchiveResult(
                        "snapshot-1", SnapshotModel.Status.ARCHIVED, "reconciliation-1");
        when(archives.archive(any())).thenReturn(archived);
        var report = new SnapshotProvisionalRootReconciler.ReconciliationReport(
                2, 1, 1, java.util.List.of());
        when(reconciler.reconcile("org-a", 25)).thenReturn(report);

        assertEquals(archived, controller.archive("org-a", "snapshot-1",
                new SnapshotController.ArchiveRequest("repo-1", "archive-1")));
        verify(archives).archive(new SnapshotArchiveService.ArchiveRequest(
                "org-a", "repo-1", "snapshot-1", "archive-1"));
        assertEquals(report, controller.reconcileRoots("org-a", 25));
        verify(reconciler).reconcile("org-a", 25);
        assertThrows(SecurityException.class, () -> controller.archive(
                "", "snapshot-1",
                new SnapshotController.ArchiveRequest("repo-1", "archive-2")));
    }

    private static void bindPrincipal(String organizationId, Set<String> permissions) {
        var grant = new ControlPlanePrincipal.TenantGrant(Set.of("OPERATOR"), permissions);
        var principal = new ControlPlanePrincipal(
                organizationId, "actor-1", Set.of("OPERATOR"), permissions,
                Map.of(organizationId, grant));
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setAttribute(OidcTenantMembershipFilter.PRINCIPAL_ATTRIBUTE, principal);
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
    }
}
