package io.elmos.controlplane;

/**
 * The operations credential is absent or malformed, so the endpoint cannot
 * decide anything about the caller.
 *
 * <p>Distinct from {@link SecurityException} on purpose: that one means "you
 * are not allowed", this one means "this deployment was never configured to
 * answer". They map to different status codes because an operator debugging a
 * 503 looks at configuration and an operator debugging a 403 looks at
 * credentials, and conflating them sends them to the wrong place.
 *
 * <p>Lifted out of {@code OperationsObservabilityController}, where it was a
 * private nested class, when authorization moved to
 * {@link OperationsAuthorization}. It stays package-private: it is an internal
 * signal between the authorizer and the controllers that map it, not part of
 * any API.
 */
final class ObservabilityUnavailableException extends RuntimeException {
}
