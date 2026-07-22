---
name: unified-scm-domain-contract-capability-and-error-model
description: "Implement the provider-neutral SCM domain model, connector interfaces, capability registry, stable identities, pagination, normalized errors, namespace/repository/ref/review/status contracts, and adapter TCK."
---

# Objective

Define one stable core contract that every SCM adapter implements.

# Core provider interface

Implement an interface similar to:

```java
public interface ScmConnector {
    ScmProviderType providerType();

    ScmProviderDiscovery discover(
        ScmProviderContext context
    );

    ScmAuthorizationResult validateAuthorization(
        ScmAuthorizationContext context
    );

    ScmPage<ScmNamespaceSnapshot> listNamespaces(
        ScmRequestContext context,
        ScmPageRequest page
    );

    ScmPage<ScmRepositorySnapshot> listRepositories(
        ScmRequestContext context,
        ScmNamespaceRef namespace,
        ScmPageRequest page
    );

    ScmRepositorySnapshot getRepository(
        ScmRequestContext context,
        ScmRepositoryNativeId repository
    );

    ScmPage<ScmRefSnapshot> listRefs(
        ScmRequestContext context,
        ScmRepositoryNativeId repository,
        ScmRefQuery query,
        ScmPageRequest page
    );

    ScmBranchPolicySnapshot getBranchPolicy(
        ScmRequestContext context,
        ScmRepositoryNativeId repository,
        ScmRefName branch
    );

    ScmWebhookSubscriptionResult ensureWebhook(
        ScmWebhookSubscriptionCommand command
    );

    ScmCredentialLease issueCredential(
        ScmCredentialLeaseRequest request
    );

    ScmReviewRequestResult createReviewRequest(
        ScmCreateReviewRequestCommand command
    );

    ScmStatusResult publishCommitStatus(
        ScmPublishStatusCommand command
    );

    ScmReconciliationResult reconcile(
        ScmReconciliationCommand command
    );
}
