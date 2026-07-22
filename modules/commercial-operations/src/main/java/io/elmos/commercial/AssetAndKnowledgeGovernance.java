package io.elmos.commercial;

import io.elmos.commercial.CommercialModels.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public final class AssetAndKnowledgeGovernance {

    public AssetDecision evaluateListing(RecipeAsset asset, AssetVisibility requestedVisibility,
                                         boolean positiveNegativeTestsPassed, boolean canaryPassed,
                                         boolean maintainerAssigned) {
        List<String> reasons = new ArrayList<>();
        boolean privateOrigin = Set.of("CUSTOMER_PRIVATE", "CUSTOMER_CONTRIBUTED").contains(asset.origin());
        if (privateOrigin && requestedVisibility != AssetVisibility.PRIVATE && !asset.customerPublicationApproved()) {
            reasons.add("CUSTOMER_PUBLICATION_APPROVAL_REQUIRED");
        }
        if (!asset.licenseApproved()) reasons.add("LICENSE_NOT_APPROVED");
        if (!asset.sbomPresent()) reasons.add("SBOM_MISSING");
        if (!asset.signed()) reasons.add("SIGNATURE_MISSING");
        if (!asset.idempotent()) reasons.add("IDEMPOTENCE_NOT_PROVEN");
        if (!asset.securityReviewed()) reasons.add("SECURITY_REVIEW_MISSING");
        if (!positiveNegativeTestsPassed) reasons.add("REGRESSION_TESTS_NOT_PASSED");
        if (!canaryPassed) reasons.add("CANARY_NOT_PASSED");
        if (!maintainerAssigned) reasons.add("MAINTAINER_REQUIRED");
        boolean allowed = reasons.isEmpty();
        AssetVisibility visibility = allowed ? requestedVisibility : AssetVisibility.PRIVATE;
        AssetCertification certification = allowed ? AssetCertification.ELMOS_CERTIFIED : AssetCertification.UNVERIFIED;
        return new AssetDecision(allowed, visibility, certification, reasons);
    }

    public AssetDecision recall(RecipeAsset asset, String reasonCode) {
        CommercialModels.require(reasonCode, "reasonCode");
        return new AssetDecision(false, asset.visibility(), AssetCertification.BLOCKED,
                List.of("ASSET_RECALLED", reasonCode, "NEW_INSTALL_AND_EXECUTION_BLOCKED", "HISTORICAL_EVIDENCE_PRESERVED"));
    }

    public KnowledgeDecision evaluateKnowledge(KnowledgeArticle article, String requestingOrganizationId,
                                               boolean versionCompatible, boolean sourceStillApproved) {
        List<String> reasons = new ArrayList<>();
        boolean privateVisibility = Set.of("ORGANIZATION_PRIVATE", "PROJECT_PRIVATE").contains(article.visibility());
        if (privateVisibility && !article.organizationId().equals(requestingOrganizationId)) reasons.add("KNOWLEDGE_TENANT_MISMATCH");
        if (!versionCompatible) reasons.add("KNOWLEDGE_VERSION_INCOMPATIBLE");
        if (!sourceStillApproved) reasons.add("KNOWLEDGE_SOURCE_REVOKED");
        if (Set.of(KnowledgeTrust.DRAFT, KnowledgeTrust.AI_GENERATED, KnowledgeTrust.DEPRECATED,
                KnowledgeTrust.REVOKED).contains(article.trust())) reasons.add("KNOWLEDGE_TRUST_INSUFFICIENT");
        if (article.trust() == KnowledgeTrust.EVIDENCE_BACKED && article.evidenceRefs().isEmpty()) reasons.add("EVIDENCE_REFERENCE_REQUIRED");
        if (!privateVisibility && (!article.anonymized() || !article.humanApproved())) reasons.add("ANONYMIZATION_AND_REVIEW_REQUIRED");
        String sanitized = sanitize(article.sourceText());
        if (!privateVisibility && containsCustomerIdentifiers(sanitized)) reasons.add("CUSTOMER_IDENTIFIER_REMAINS");
        return new KnowledgeDecision(reasons.isEmpty(), reasons.isEmpty() ? article.trust() : KnowledgeTrust.DRAFT,
                reasons, sanitized);
    }

    private static String sanitize(String text) {
        if (text == null) return "";
        return text.replaceAll("(?i)(https?://)?[a-z0-9.-]+\\.(internal|corp|local)(:[0-9]+)?", "[private-endpoint]")
                .replaceAll("(?i)com\\.[a-z0-9_.]+", "example.migrated")
                .replaceAll("(?i)(customer|company|repository)\\s*[:=]\\s*[^\\s,;]+", "$1=[redacted]");
    }
    private static boolean containsCustomerIdentifiers(String text) {
        return text.matches("(?s).*(\\.internal|\\.corp|\\.local|github\\.com/[^/\\s]+/[^/\\s]+).*" );
    }
}
