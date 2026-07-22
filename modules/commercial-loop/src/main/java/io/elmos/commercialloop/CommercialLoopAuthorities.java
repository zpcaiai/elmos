package io.elmos.commercialloop;

import static io.elmos.commercialloop.CommercialLoopModels.*;

/**
 * Evidence-only ports for CRM, POC, CPQ/contract, platform onboarding, delivery, support,
 * partner and finance systems. This module never creates leads, quotes, orders, invoices,
 * tenants, tickets, settlements or production changes.
 */
public record CommercialLoopAuthorities(
        SalesPocAuthority salesPoc,
        QuoteContractAuthority quoteContract,
        OnboardingDeliveryAuthority onboardingDelivery,
        SupportSuccessAuthority supportSuccess,
        PartnerAuthority partner,
        OperationsEconomicsAuthority operationsEconomics,
        ScaleAcceptanceAuthority scaleAcceptance) {
    public CommercialLoopAuthorities {
        CommercialLoopModels.required(salesPoc, "sales/POC authority");
        CommercialLoopModels.required(quoteContract, "quote/contract authority");
        CommercialLoopModels.required(onboardingDelivery, "onboarding/delivery authority");
        CommercialLoopModels.required(supportSuccess, "support/success authority");
        CommercialLoopModels.required(partner, "partner authority");
        CommercialLoopModels.required(operationsEconomics, "operations/economics authority");
        CommercialLoopModels.required(scaleAcceptance, "scale acceptance authority");
    }

    @FunctionalInterface public interface SalesPocAuthority { SalesPocEvidence observe(Request request); }
    @FunctionalInterface public interface QuoteContractAuthority { QuoteContractEvidence observe(Request request); }
    @FunctionalInterface public interface OnboardingDeliveryAuthority { OnboardingDeliveryEvidence observe(Request request); }
    @FunctionalInterface public interface SupportSuccessAuthority { SupportSuccessEvidence observe(Request request); }
    @FunctionalInterface public interface PartnerAuthority { PartnerEvidence observe(Request request); }
    @FunctionalInterface public interface OperationsEconomicsAuthority { OperationsEconomicsEvidence observe(Request request); }
    @FunctionalInterface public interface ScaleAcceptanceAuthority { ScaleAcceptanceEvidence observe(Request request); }
}
