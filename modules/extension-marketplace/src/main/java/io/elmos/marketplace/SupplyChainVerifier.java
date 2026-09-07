package io.elmos.marketplace;

import java.security.GeneralSecurityException;
import java.security.Signature;
import static io.elmos.marketplace.MarketplaceModels.*;

public final class SupplyChainVerifier {
    public PolicyDecision verify(SupplyChainEnvelope envelope) {
        if (!Digests.exact(envelope.expectedDigest()) || !Digests.sha256(envelope.artifact()).equals(envelope.expectedDigest())) return PolicyDecision.deny("ARTIFACT_DIGEST_MISMATCH");
        if (!Digests.exact(envelope.sbomDigest()) || !Digests.exact(envelope.provenanceDigest())) return PolicyDecision.deny("SBOM_AND_PROVENANCE_REQUIRED");
        if (envelope.publicKey()==null || envelope.signature().length==0) return PolicyDecision.deny("SIGNATURE_REQUIRED");
        try {
            Signature verifier=Signature.getInstance("Ed25519"); verifier.initVerify(envelope.publicKey()); verifier.update(envelope.artifact());
            if (!verifier.verify(envelope.signature())) return PolicyDecision.deny("SIGNATURE_INVALID");
        } catch (GeneralSecurityException error) { return PolicyDecision.deny("SIGNATURE_VERIFICATION_ERROR"); }
        return PolicyDecision.allow("SUPPLY_CHAIN_VERIFIED",envelope.expectedDigest());
    }
}
