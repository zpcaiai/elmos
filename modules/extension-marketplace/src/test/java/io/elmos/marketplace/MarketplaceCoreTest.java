package io.elmos.marketplace;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.util.List;
import java.util.Set;

import static io.elmos.marketplace.MarketplaceModels.*;
import static org.junit.jupiter.api.Assertions.*;

class MarketplaceCoreTest {
    private static final byte[] ARTIFACT="extension-artifact".getBytes(StandardCharsets.UTF_8);
    private static final String DIGEST=Digests.sha256(ARTIFACT);

    @Test void exactManifestIsAccepted() {
        assertEquals(Decision.ALLOW,new ExtensionManifestValidator().validate(manifest("tenant-a",Set.of("artifact:read"))).decision());
    }
    @Test void unknownOrWildcardPermissionsAreRejected() {
        var validator=new ExtensionManifestValidator();
        assertEquals("UNDECLARED_OR_UNKNOWN_PERMISSION",validator.validate(manifest("tenant-a",Set.of("root:host"))).code());
        assertEquals("UNDECLARED_OR_UNKNOWN_PERMISSION",validator.validate(manifest("tenant-a",Set.of("*"))).code());
    }
    @Test void manifestRequiresExactSemverAndDigest() {
        var invalid=new ExtensionManifest("sample.publisher.ext","publisher","latest","1.0", "latest","tenant-a",Set.of(),Set.of("run"));
        assertEquals("EXACT_VERSION_REQUIRED",new ExtensionManifestValidator().validate(invalid).code());
    }
    @Test void sandboxIsDefaultDenyAndRejectsPrivilege() {
        var engine=new SandboxPolicyEngine();
        assertEquals(Decision.ALLOW,engine.validate(sandbox()).decision());
        assertEquals("SANDBOX_DEFAULT_DENY_REQUIRED",engine.validate(new SandboxPolicy("allow",Set.of(),Set.of("workspace"),Set.of(),Set.of(),false,false)).code());
        assertEquals("PRIVILEGED_EXECUTION_DENIED",engine.validate(new SandboxPolicy("deny",Set.of(),Set.of("workspace"),Set.of(),Set.of(),true,false)).code());
    }
    @Test void sandboxRejectsWildcardNetworkAndHostPaths() {
        var engine=new SandboxPolicyEngine();
        assertEquals("WILDCARD_NETWORK_DENIED",engine.validate(new SandboxPolicy("deny",Set.of("*"),Set.of("workspace"),Set.of(),Set.of(),false,false)).code());
        assertEquals("HOST_PATH_DENIED",engine.validate(new SandboxPolicy("deny",Set.of(),Set.of("/etc"),Set.of(),Set.of(),false,false)).code());
    }
    @Test void sandboxAuthorizationIsTenantAndPermissionExact() {
        var engine=new SandboxPolicyEngine();
        assertEquals("CROSS_TENANT_EXECUTION_DENIED",engine.authorize(manifest("tenant-a",Set.of("artifact:read")),sandbox(),"tenant-b","artifact:read").code());
        assertEquals("PERMISSION_NOT_DECLARED",engine.authorize(manifest("tenant-a",Set.of("artifact:read")),sandbox(),"tenant-a","artifact:write").code());
    }
    @Test void compatibilityRejectsPrivateAndUnsupportedApis() {
        var engine=new CompatibilityEngine();
        assertEquals("PRIVATE_API_NOT_A_COMPATIBILITY_PROMISE",engine.evaluate(new CompatibilityContract("2.0.0","1.0.0","1.0.0",Set.of("2.0.0"),false,0),"2.0.0",0).code());
        assertEquals("PRODUCT_VERSION_UNSUPPORTED",engine.evaluate(new CompatibilityContract("2.0.0","1.0.0","1.0.0",Set.of("2.0.0"),true,0),"1.0.0",0).code());
    }
    @Test void compatibilityBindsExactTupleAndDeprecation() {
        var engine=new CompatibilityEngine();
        assertEquals(Decision.ALLOW,engine.evaluate(new CompatibilityContract("2.0.0","1.0.0","1.2.0",Set.of("2.0.0"),true,200),"2.0.0",100).decision());
        assertEquals("DEPRECATION_EXIT_REACHED",engine.evaluate(new CompatibilityContract("2.0.0","1.0.0","1.2.0",Set.of("2.0.0"),true,100),"2.0.0",100).code());
    }
    @Test void supplyChainUsesRealEd25519AndDigestVerification() throws Exception {
        var pair=KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        var signer=Signature.getInstance("Ed25519"); signer.initSign(pair.getPrivate()); signer.update(ARTIFACT);
        var envelope=new SupplyChainEnvelope(ARTIFACT,signer.sign(),pair.getPublic(),DIGEST,Digests.sha256("sbom".getBytes()),Digests.sha256("provenance".getBytes()));
        assertEquals(Decision.ALLOW,new SupplyChainVerifier().verify(envelope).decision());
    }
    @Test void tamperedArtifactCannotReuseSignature() throws Exception {
        var pair=KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        var signer=Signature.getInstance("Ed25519"); signer.initSign(pair.getPrivate()); signer.update(ARTIFACT); byte[] signature=signer.sign();
        var envelope=new SupplyChainEnvelope("tampered".getBytes(),signature,pair.getPublic(),DIGEST,Digests.sha256("sbom".getBytes()),Digests.sha256("provenance".getBytes()));
        assertEquals("ARTIFACT_DIGEST_MISMATCH",new SupplyChainVerifier().verify(envelope).code());
    }
    @Test void publisherRequiresIndependentVerifiedIdentityAndKeys() {
        var registry=new PublisherRegistry();
        assertEquals(Decision.ALLOW,registry.validate(new PublisherProfile("publisher",true,true,true,true,Set.of("registry:e1"),Set.of("key-1"),"security@example.invalid")).decision());
        assertEquals("PUBLISHER_SECURITY_CONTROLS_REQUIRED",registry.validate(new PublisherProfile("publisher",true,true,false,false,Set.of("e"),Set.of("key"),"security@example.invalid")).code());
    }
    @Test void dependencyLockRejectsCyclesFloatingAndRevokedNodes() {
        var resolver=new DependencyLockResolver();
        assertEquals(Decision.ALLOW,resolver.validate(List.of(new Dependency("a","1.0.0",DIGEST,Set.of(),false),new Dependency("b","1.0.0",DIGEST,Set.of("a"),false))).decision());
        assertEquals("DEPENDENCY_CYCLE",resolver.validate(List.of(new Dependency("a","1.0.0",DIGEST,Set.of("b"),false),new Dependency("b","1.0.0",DIGEST,Set.of("a"),false))).code());
        assertEquals("FLOATING_OR_UNPINNED_DEPENDENCY",resolver.validate(List.of(new Dependency("a","*",DIGEST,Set.of(),false))).code());
        assertEquals("REVOKED_DEPENDENCY",resolver.validate(List.of(new Dependency("a","1.0.0",DIGEST,Set.of(),true))).code());
    }

    private ExtensionManifest manifest(String tenant,Set<String> permissions) { return new ExtensionManifest("sample.publisher.ext","publisher","1.0.0","2.0.0",DIGEST,tenant,permissions,Set.of("extension.run")); }
    private SandboxPolicy sandbox() { return new SandboxPolicy("deny",Set.of("api.example.invalid:443"),Set.of("workspace"),Set.of("compiler"),Set.of("lease:signing"),false,false); }
}
