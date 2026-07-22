package io.elmos.ecosystemgrowth;

import static io.elmos.ecosystemgrowth.EcosystemGrowthModels.*;

/** Evidence-only G14 authority ports. Implementations observe systems of record without mutating them. */
public record EcosystemGrowthAuthorities(
        ProductActivationAuthority productActivation,
        ContentDeveloperAuthority contentDeveloper,
        CommunitySafetyAuthority communitySafety,
        MarketplaceGrowthAuthority marketplaceGrowth,
        InternationalizationAuthority internationalization,
        RegionalChannelAuthority regionalChannel,
        GrowthConformanceAuthority growthConformance) {
    public EcosystemGrowthAuthorities {
        required(productActivation, "productActivation");
        required(contentDeveloper, "contentDeveloper");
        required(communitySafety, "communitySafety");
        required(marketplaceGrowth, "marketplaceGrowth");
        required(internationalization, "internationalization");
        required(regionalChannel, "regionalChannel");
        required(growthConformance, "growthConformance");
    }

    @FunctionalInterface public interface ProductActivationAuthority { GateEvidence observe(Request request); }
    @FunctionalInterface public interface ContentDeveloperAuthority { GateEvidence observe(Request request); }
    @FunctionalInterface public interface CommunitySafetyAuthority { GateEvidence observe(Request request); }
    @FunctionalInterface public interface MarketplaceGrowthAuthority { GateEvidence observe(Request request); }
    @FunctionalInterface public interface InternationalizationAuthority { GateEvidence observe(Request request); }
    @FunctionalInterface public interface RegionalChannelAuthority { GateEvidence observe(Request request); }
    @FunctionalInterface public interface GrowthConformanceAuthority {
        GrowthConformanceEvidence observe(Request request);
    }
}
