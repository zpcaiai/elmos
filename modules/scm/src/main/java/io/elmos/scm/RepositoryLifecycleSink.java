package io.elmos.scm;

/**
 * Receives provider-authoritative repository deletion events after their delivery has been
 * signature-verified and tenant-bound. Implementations must be idempotent: webhook redelivery is
 * expected and the first lifecycle transition may already have committed when an outbox
 * acknowledgement is lost.
 */
@FunctionalInterface
public interface RepositoryLifecycleSink {

    /**
     * Permanently fences the current repository incarnation. Implementations must not finalize
     * or delete bindings until all snapshot roots have been reconciled.
     */
    void onRepositoryDeleted(
            String organizationId,
            WebhookIngestionService.Delivery delivery
    );
}
