package io.elmos.commercialapi;

import java.sql.SQLException;
import java.util.Set;

/**
 * Keeps database diagnostic parsing outside the public exception boundary.
 *
 * <p>The caller exposes only a stable allowlisted domain code and a fixed
 * response message. PostgreSQL diagnostics never cross the HTTP boundary.
 */
final class PostgresBillingDomainErrorClassifier {
    private PostgresBillingDomainErrorClassifier() {
    }

    static String classify(SQLException error, Set<String> allowlistedCodes) {
        if (error == null) {
            return null;
        }
        String diagnostic = error.getMessage();
        if (diagnostic == null) {
            return null;
        }
        return allowlistedCodes.stream()
                .filter(diagnostic::contains)
                .findFirst()
                .orElse(null);
    }
}
