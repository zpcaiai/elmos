package io.elmos.platform;

import static io.elmos.platform.EnterprisePlatformModels.*;

/**
 * Approved enterprise evidence ports. Implementations integrate with IAM, Runner, model, billing,
 * KMS, deployment and DR systems outside this policy module; this module never provisions tenants,
 * executes customer code, accesses keys, charges customers or installs production infrastructure.
 */
public record EnterprisePlatformAuthorities(
        TenancyIdentityAuthority tenancyIdentity,
        AuthorizationAuditAuthority authorizationAudit,
        RunnerSecurityAuthority runnerSecurity,
        ModelCostAuthority modelCost,
        DataGovernanceAuthority dataGovernance,
        DeploymentAuthority deployment,
        EnterpriseAcceptanceAuthority enterpriseAcceptance) {
    public EnterprisePlatformAuthorities {
        EnterprisePlatformModels.required(tenancyIdentity, "tenancy/identity authority");
        EnterprisePlatformModels.required(authorizationAudit, "authorization/audit authority");
        EnterprisePlatformModels.required(runnerSecurity, "runner security authority");
        EnterprisePlatformModels.required(modelCost, "model/cost authority");
        EnterprisePlatformModels.required(dataGovernance, "data governance authority");
        EnterprisePlatformModels.required(deployment, "deployment authority");
        EnterprisePlatformModels.required(enterpriseAcceptance, "enterprise acceptance authority");
    }

    @FunctionalInterface public interface TenancyIdentityAuthority { TenancyIdentityEvidence observe(Request request); }
    @FunctionalInterface public interface AuthorizationAuditAuthority { AuthorizationAuditEvidence observe(Request request); }
    @FunctionalInterface public interface RunnerSecurityAuthority { RunnerSecurityEvidence observe(Request request); }
    @FunctionalInterface public interface ModelCostAuthority { ModelCostEvidence observe(Request request); }
    @FunctionalInterface public interface DataGovernanceAuthority { DataGovernanceEvidence observe(Request request); }
    @FunctionalInterface public interface DeploymentAuthority { DeploymentEvidence observe(Request request); }
    @FunctionalInterface public interface EnterpriseAcceptanceAuthority { EnterpriseAcceptanceEvidence observe(Request request); }
}
