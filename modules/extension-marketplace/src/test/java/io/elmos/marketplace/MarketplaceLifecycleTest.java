package io.elmos.marketplace;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.Set;

import static io.elmos.marketplace.MarketplaceModels.*;
import static org.junit.jupiter.api.Assertions.*;

class MarketplaceLifecycleTest {
    private static final String DIGEST=Digests.sha256("release".getBytes(StandardCharsets.UTF_8));

    @Test void releaseStateMachineRequiresIndependentApproval() {
        var service=new ReleaseLifecycleService();
        assertEquals("INDEPENDENT_RELEASE_APPROVAL_REQUIRED",service.transition(release(ReleaseStatus.SUBMITTED),ReleaseStatus.CERTIFIED,false).code());
        assertEquals(Decision.ALLOW,service.transition(release(ReleaseStatus.SUBMITTED),ReleaseStatus.CERTIFIED,true).decision());
    }
    @Test void releaseStateMachineRejectsInvalidTransitions() {
        assertEquals("INVALID_RELEASE_TRANSITION",new ReleaseLifecycleService().transition(release(ReleaseStatus.DRAFT),ReleaseStatus.PUBLISHED,true).code());
    }
    @Test void revokedQuarantinedAndUnpublishedReleasesNeverExecute() {
        var service=new ReleaseLifecycleService();
        assertEquals(Decision.ALLOW,service.executable(release(ReleaseStatus.PUBLISHED)).decision());
        assertEquals("RELEASE_EXECUTION_BLOCKED",service.executable(release(ReleaseStatus.REVOKED)).code());
        assertEquals("RELEASE_EXECUTION_BLOCKED",service.executable(release(ReleaseStatus.QUARANTINED)).code());
        assertEquals("RELEASE_NOT_PUBLISHED",service.executable(release(ReleaseStatus.CERTIFIED)).code());
    }
    @Test void installationIsTenantScopedAndIdempotent() {
        var registry=new InstallationRegistry(); var manifest=manifest("tenant-a");
        var request=new InstallationRequest("key-1","tenant-a",manifest.extensionId(),DIGEST,Set.of("artifact:read"),true,false);
        assertEquals("INSTALLATION_CREATED",registry.install(request,manifest).code());
        assertEquals("INSTALLATION_REPLAYED",registry.install(request,manifest).code());
        assertEquals("CROSS_TENANT_INSTALL_DENIED",registry.install(new InstallationRequest("key-2","tenant-b",manifest.extensionId(),DIGEST,Set.of(),true,false),manifest).code());
    }
    @Test void installationRejectsPermissionEscalationAndIdempotencyConflict() {
        var registry=new InstallationRegistry(); var manifest=manifest("tenant-a");
        assertEquals("PERMISSION_ESCALATION_DENIED",registry.install(new InstallationRequest("key-1","tenant-a",manifest.extensionId(),DIGEST,Set.of("artifact:write"),true,false),manifest).code());
        assertEquals("INSTALLATION_CREATED",registry.install(new InstallationRequest("key-1","tenant-a",manifest.extensionId(),DIGEST,Set.of(),true,false),manifest).code());
        assertEquals("IDEMPOTENCY_KEY_CONFLICT",registry.install(new InstallationRequest("key-1","tenant-a",manifest.extensionId(),Digests.sha256("other".getBytes()),Set.of(),true,false),manifest("tenant-a",Digests.sha256("other".getBytes()))).code());
    }
    @Test void revocationIsTenantScoped() {
        var registry=new InstallationRegistry(); var manifest=manifest("tenant-a");
        registry.install(new InstallationRequest("key-1","tenant-a",manifest.extensionId(),DIGEST,Set.of(),true,false),manifest);
        assertEquals("INSTALLATION_NOT_FOUND_IN_TENANT",registry.revoke("key-1","tenant-b").code());
        assertEquals("INSTALLATION_REVOKED",registry.revoke("key-1","tenant-a").code());
    }
    @Test void runtimeReconciliationFailsOnDriftAndLeaks() {
        var controls=new MarketplaceClosureControls();
        assertEquals(Decision.ALLOW,controls.reconcileRuntime(new RuntimeHealth(DIGEST,DIGEST,0,0,0,false)).decision());
        assertEquals("RUNTIME_DIGEST_DRIFT",controls.reconcileRuntime(new RuntimeHealth(DIGEST,Digests.sha256("other".getBytes()),0,0,0,false)).code());
        assertEquals("RUNTIME_RECONCILIATION_INCOMPLETE",controls.reconcileRuntime(new RuntimeHealth(DIGEST,DIGEST,0,1,0,false)).code());
    }
    @Test void offlineMirrorCannotCreateRightsOrUseStaleRevocationState() {
        var controls=new MarketplaceClosureControls();
        var valid=new OfflineMirror(DIGEST,DIGEST,"root",Set.of("root"),Set.of("artifact:read"),Set.of("artifact:read"),10,60,true,false);
        assertEquals(Decision.ALLOW,controls.verifyOfflineMirror(valid).decision());
        assertEquals("OFFLINE_RIGHTS_EXPANSION_DENIED",controls.verifyOfflineMirror(new OfflineMirror(DIGEST,DIGEST,"root",Set.of("root"),Set.of("artifact:write"),Set.of("artifact:read"),10,60,true,false)).code());
        assertEquals("OFFLINE_REVOCATION_STATE_STALE",controls.verifyOfflineMirror(new OfflineMirror(DIGEST,DIGEST,"root",Set.of("root"),Set.of(),Set.of(),61,60,true,false)).code());
    }
    @Test void settlementUsesExactDecimalConservation() {
        var controls=new MarketplaceClosureControls();
        var valid=new Settlement(d("100.00"),d("5.00"),d("10.00"),d("60.00"),d("20.00"),d("5.00"),d("100.00"),false);
        assertEquals(Decision.ALLOW,controls.reconcileSettlement(valid).decision());
        assertEquals("SETTLEMENT_CONSERVATION_BROKEN",controls.reconcileSettlement(new Settlement(d("100.00"),d("5.00"),d("10.00"),d("60.00"),d("20.00"),d("4.99"),d("100.00"),false)).code());
    }
    @Test void settlementFailsClosedOnOpenFraud() {
        assertEquals("OPEN_FRAUD_FINDING",new MarketplaceClosureControls().reconcileSettlement(new Settlement(d("1"),d("0"),d("0"),d("0"),d("1"),d("0"),d("1"),true)).code());
    }
    @Test void eolRequiresNotificationsPortabilityUninstallAndDependencyDrain() {
        var controls=new MarketplaceClosureControls();
        Set<String> tenants=Set.of("tenant-a");
        assertEquals(Decision.ALLOW,controls.validateEol(new EolPlan(tenants,tenants,tenants,tenants,Set.of(),true)).decision());
        assertEquals("CUSTOMER_NOTIFICATION_INCOMPLETE",controls.validateEol(new EolPlan(tenants,Set.of(),tenants,tenants,Set.of(),true)).code());
        assertEquals("RESIDUAL_EOL_DEPENDENCIES",controls.validateEol(new EolPlan(tenants,tenants,tenants,tenants,Set.of("dependency-a"),true)).code());
    }
    @Test void eolWithoutReplacementEscalatesInsteadOfAutoApproving() {
        Set<String> tenants=Set.of("tenant-a");
        assertEquals(Decision.ESCALATE,new MarketplaceClosureControls().validateEol(new EolPlan(tenants,tenants,tenants,tenants,Set.of(),false)).decision());
    }

    private ReleaseRecord release(ReleaseStatus status) { return new ReleaseRecord("sample@1.0.0","sample.publisher.ext","publisher",status,DIGEST,true,Digests.sha256("sbom".getBytes()),Digests.sha256("provenance".getBytes())); }
    private ExtensionManifest manifest(String tenant) { return manifest(tenant,DIGEST); }
    private ExtensionManifest manifest(String tenant,String digest) { return new ExtensionManifest("sample.publisher.ext","publisher","1.0.0","2.0.0",digest,tenant,Set.of("artifact:read"),Set.of("run")); }
    private BigDecimal d(String value) { return new BigDecimal(value); }
}
