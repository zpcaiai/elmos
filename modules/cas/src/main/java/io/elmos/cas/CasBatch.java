package io.elmos.cas;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * ELMOS-CAS-011. Batch transfer shapes.
 *
 * <p>A batch is not a loop with a nicer name. The two properties that make it worth having are
 * both about failure and both are easy to get wrong:
 *
 * <ol>
 *   <li><b>One existence probe for the whole set.</b> Uploading 4000 dependency blobs one at a
 *       time means 4000 round trips to discover that 3990 of them are already there.</li>
 *   <li><b>Partial failure does not abort the batch.</b> If object 300 of 500 is corrupt, the
 *       other 499 must still land and the caller must learn precisely which one failed and why.
 *       An all-or-nothing batch turns one bad object into a retry of the entire transfer, which
 *       is how a slow incident becomes a stuck one.</li>
 * </ol>
 */
public final class CasBatch {

    private CasBatch() {
    }

    public record WriteItem(CasDigest digest, byte[] content) {
        public WriteItem {
            Objects.requireNonNull(digest, "digest");
            content = content.clone();
        }

        @Override
        public byte[] content() {
            return content.clone();
        }
    }

    /**
     * @param written               objects this call actually stored
     * @param skippedAlreadyPresent objects the store already held; the bytes were never sent again
     * @param failed                digest to failure reason, in submission order
     */
    public record WriteResult(List<CasDigest> written,
                              List<CasDigest> skippedAlreadyPresent,
                              Map<CasDigest, String> failed) {
        public WriteResult {
            written = List.copyOf(written);
            skippedAlreadyPresent = List.copyOf(skippedAlreadyPresent);
            failed = Map.copyOf(new LinkedHashMap<>(failed));
        }

        public boolean complete() {
            return failed.isEmpty();
        }

        public long bytesSkipped() {
            return skippedAlreadyPresent.stream().mapToLong(CasDigest::sizeBytes).sum();
        }
    }

    public record ReadResult(Map<CasDigest, byte[]> found,
                             List<CasDigest> missing,
                             Map<CasDigest, String> failed) {
        public ReadResult {
            found = Map.copyOf(new LinkedHashMap<>(found));
            missing = List.copyOf(missing);
            failed = Map.copyOf(new LinkedHashMap<>(failed));
        }

        public boolean complete() {
            return missing.isEmpty() && failed.isEmpty();
        }
    }
}
