# Suggested Java module layout

```text
elmos-release-deployment/
  release-domain/
  deployment-domain/
  deployment-application/
  deployment-policy/
  deployment-workflow-temporal/
  deployment-evidence/
  adapter-alibaba-sts/
  adapter-alibaba-ecs/
  adapter-alibaba-acr/
  adapter-alibaba-kms/
  adapter-docker-host/
  adapter-observability-otel/
  deployment-api/
```

## Core SPIs

```java
public interface DeploymentProvider {
    ProviderCapabilities probe(DeploymentTarget target, CapabilityLease lease);
    PreparedTarget preflight(DeploymentPlan plan, CapabilityLease lease);
    ProviderDeploymentResult apply(DeploymentPlan plan, CapabilityLease lease);
    ObservedDeploymentState observe(DeploymentId id, DeploymentTarget target, CapabilityLease lease);
}

public interface RemoteExecutor {
    RemoteInvocation submit(CommandTemplate template, CommandArguments args, ExecutionTarget target, CapabilityLease lease);
    RemoteInvocationResult await(RemoteInvocation invocation);
}

public interface HealthVerifier {
    VerificationResult verify(HealthPolicy policy, ObservedDeploymentState state);
}

public interface RollbackManager {
    RollbackPlan planRollback(DeploymentSnapshot before, ObservedDeploymentState current);
    RollbackResult rollback(RollbackPlan plan, CapabilityLease lease);
}
```

Keep Alibaba SDK request/response objects out of domain interfaces.
