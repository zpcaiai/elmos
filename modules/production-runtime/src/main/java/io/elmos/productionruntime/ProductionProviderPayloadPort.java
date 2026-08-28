package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;

import java.util.Arrays;
import java.util.Objects;

/**
 * Loads the exact, already-durable provider request bytes for a model call.
 *
 * <p>The provider adapter deliberately receives only a digest in
 * {@link ModelCallRequest}.  This port prevents a retry from regenerating a
 * prompt that might differ from the request whose idempotency receipt was
 * committed.</p>
 */
public interface ProductionProviderPayloadPort {
    MaterializedPayload materialize(ModelCallRequest request);

    record MaterializedPayload(byte[] bytes, String mediaType) {
        public MaterializedPayload {
            Objects.requireNonNull(bytes, "bytes");
            if (bytes.length == 0 || bytes.length > 1_048_576) {
                throw new IllegalArgumentException("provider payload must be between 1 byte and 1 MiB");
            }
            bytes = Arrays.copyOf(bytes, bytes.length);
            if (!"application/json".equals(mediaType)) {
                throw new IllegalArgumentException("only application/json provider payloads are supported");
            }
        }

        @Override
        public byte[] bytes() {
            return Arrays.copyOf(bytes, bytes.length);
        }
    }
}
