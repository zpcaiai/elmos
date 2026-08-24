package io.elmos.cas;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Date;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;

/**
 * ELMOS-CAS-026. Turns a presented mTLS certificate chain into an attested workload identity.
 *
 * <p>{@link ActionCache} refuses writes from an identity whose {@code attested} flag is false.
 * Until now that flag arrived from the caller, which made it a promise rather than a fact. This
 * class is what produces it, and it is the only thing that should.
 *
 * <p>What is actually checked, and why each one matters:
 *
 * <ul>
 *   <li><b>PKIX path validation against a pinned trust bundle.</b> Not the JVM default trust
 *       store — a runner identity signed by a public CA is not a runner identity. The bundle is
 *       one trust domain's roots and nothing else.</li>
 *   <li><b>Validity at the verification instant</b>, passed in rather than read from the system
 *       clock, so a replayed old certificate fails deterministically and the test can prove it.</li>
 *   <li><b>Exactly one SPIFFE URI SAN.</b> Two identities in one certificate is ambiguity, and
 *       ambiguity in an authorisation input resolves in the attacker's favour.</li>
 *   <li><b>Trust domain equality.</b> A valid certificate from a partner's domain is a valid
 *       certificate for the partner's cache, not for this one.</li>
 *   <li><b>clientAuth extended key usage.</b> A server certificate presented as a client identity
 *       is the classic key-reuse confusion.</li>
 *   <li><b>Serial denylist.</b> Standing in for online revocation, which needs infrastructure this
 *       module does not own; the list is authoritative and checked before anything else.</li>
 *   <li><b>Optional maximum leaf lifetime.</b> Workload certificates are supposed to be hours
 *       old. A ten-year leaf is either a misissued credential or a stolen one that nobody can
 *       rotate away.</li>
 * </ul>
 */
public final class WorkloadIdentity {

    private static final String CLIENT_AUTH_OID = "1.3.6.1.5.5.7.3.2";
    private static final int SAN_URI = 6;
    private static final String SPIFFE_SCHEME = "spiffe://";

    private WorkloadIdentity() {
    }

    public record SpiffeId(String trustDomain, String path) {
        public SpiffeId {
            trustDomain = CasText.required(trustDomain, "trustDomain");
            path = CasText.required(path, "path");
        }

        public static SpiffeId parse(String uri) {
            if (uri == null || !uri.startsWith(SPIFFE_SCHEME)) {
                throw new IllegalArgumentException("not a SPIFFE id: " + uri);
            }
            String remainder = uri.substring(SPIFFE_SCHEME.length());
            int slash = remainder.indexOf('/');
            if (slash <= 0 || slash == remainder.length() - 1) {
                throw new IllegalArgumentException("SPIFFE id needs a trust domain and a path: " + uri);
            }
            return new SpiffeId(remainder.substring(0, slash), remainder.substring(slash + 1));
        }

        public String uri() {
            return SPIFFE_SCHEME + trustDomain + "/" + path;
        }
    }

    public record Verified(SpiffeId id, String subjectDn, String serialNumber,
                           long notBeforeEpochMillis, long notAfterEpochMillis) {
    }

    public record Verdict(boolean attested, String reason, Optional<Verified> identity) {
        static Verdict deny(String reason) {
            return new Verdict(false, reason, Optional.empty());
        }

        static Verdict attest(Verified verified) {
            return new Verdict(true, "ATTESTED", Optional.of(verified));
        }
    }

    public static final class TrustBundle {
        private final String trustDomain;
        private final Set<TrustAnchor> anchors = new LinkedHashSet<>();

        public TrustBundle(String trustDomain, Collection<X509Certificate> roots) {
            this.trustDomain = CasText.required(trustDomain, "trustDomain");
            CasText.requireNonEmpty(roots, "roots");
            roots.forEach(root -> anchors.add(new TrustAnchor(root, null)));
        }

        public String trustDomain() {
            return trustDomain;
        }

        Set<TrustAnchor> anchors() {
            return Set.copyOf(anchors);
        }
    }

    public static final class Verifier {

        private final TrustBundle bundle;
        private final Set<String> revokedSerials;
        private final Optional<Long> maximumLeafLifetimeMillis;

        public Verifier(TrustBundle bundle, Set<String> revokedSerials, Optional<Long> maximumLeafLifetimeMillis) {
            this.bundle = bundle;
            this.revokedSerials = new TreeSet<>(revokedSerials);
            this.maximumLeafLifetimeMillis = maximumLeafLifetimeMillis;
        }

        public static Verifier of(TrustBundle bundle) {
            return new Verifier(bundle, Set.of(), Optional.empty());
        }

        public Verdict verify(List<X509Certificate> chain, long nowEpochMillis) {
            if (chain == null || chain.isEmpty()) {
                return Verdict.deny("NO_CERTIFICATE_PRESENTED");
            }
            X509Certificate leaf = chain.get(0);
            String serial = leaf.getSerialNumber().toString(16);
            if (revokedSerials.contains(serial)) {
                return Verdict.deny("CERTIFICATE_REVOKED");
            }
            try {
                CertificateFactory factory = CertificateFactory.getInstance("X.509");
                CertPath path = factory.generateCertPath(chain);
                PKIXParameters parameters = new PKIXParameters(bundle.anchors());
                // Online revocation needs infrastructure this module does not own; the serial
                // denylist above is the authoritative substitute and runs first.
                parameters.setRevocationEnabled(false);
                parameters.setDate(new Date(nowEpochMillis));
                CertPathValidator.getInstance("PKIX").validate(path, parameters);
            } catch (java.security.cert.CertPathValidatorException invalid) {
                return Verdict.deny("CHAIN_NOT_TRUSTED:" + invalid.getReason());
            } catch (Exception error) {
                return Verdict.deny("CHAIN_VALIDATION_FAILED:" + error.getClass().getSimpleName());
            }

            List<String> extendedKeyUsage;
            try {
                extendedKeyUsage = leaf.getExtendedKeyUsage();
            } catch (java.security.cert.CertificateParsingException error) {
                return Verdict.deny("EKU_UNPARSEABLE");
            }
            if (extendedKeyUsage == null || !extendedKeyUsage.contains(CLIENT_AUTH_OID)) {
                return Verdict.deny("CLIENT_AUTH_EKU_MISSING");
            }

            List<String> spiffeUris = spiffeUris(leaf);
            if (spiffeUris.isEmpty()) {
                return Verdict.deny("SPIFFE_SAN_MISSING");
            }
            if (spiffeUris.size() > 1) {
                return Verdict.deny("SPIFFE_SAN_AMBIGUOUS");
            }
            SpiffeId id;
            try {
                id = SpiffeId.parse(spiffeUris.get(0));
            } catch (IllegalArgumentException malformed) {
                return Verdict.deny("SPIFFE_SAN_MALFORMED");
            }
            if (!id.trustDomain().equals(bundle.trustDomain())) {
                return Verdict.deny("TRUST_DOMAIN_MISMATCH");
            }

            long notBefore = leaf.getNotBefore().getTime();
            long notAfter = leaf.getNotAfter().getTime();
            if (maximumLeafLifetimeMillis.isPresent() && notAfter - notBefore > maximumLeafLifetimeMillis.get()) {
                return Verdict.deny("LEAF_LIFETIME_TOO_LONG");
            }
            return Verdict.attest(new Verified(id, leaf.getSubjectX500Principal().getName(), serial,
                    notBefore, notAfter));
        }

        /**
         * The only supported way to produce an attested {@link ActionCache.WriterIdentity}. The
         * node id is the SPIFFE path, so quarantining a node quarantines the identity that
         * actually produced the results rather than a self-reported label.
         */
        public ActionCache.WriterIdentity attestedWriter(Verdict verdict, String serviceId) {
            if (!verdict.attested()) {
                throw new CasExceptions.CasAccessDeniedException("WRITER_NOT_ATTESTED", verdict.reason());
            }
            Verified verified = verdict.identity().orElseThrow();
            return new ActionCache.WriterIdentity(serviceId, verified.id().trustDomain(),
                    verified.id().path(), true);
        }
    }

    private static List<String> spiffeUris(X509Certificate leaf) {
        List<String> uris = new ArrayList<>();
        try {
            Collection<List<?>> names = leaf.getSubjectAlternativeNames();
            if (names == null) {
                return uris;
            }
            for (List<?> entry : names) {
                if (entry.size() >= 2 && Integer.valueOf(SAN_URI).equals(entry.get(0))
                        && String.valueOf(entry.get(1)).startsWith(SPIFFE_SCHEME)) {
                    uris.add(String.valueOf(entry.get(1)));
                }
            }
        } catch (java.security.cert.CertificateParsingException error) {
            return List.of();
        }
        return uris;
    }

    public static List<X509Certificate> parsePem(String pem) {
        try {
            CertificateFactory factory = CertificateFactory.getInstance("X.509");
            List<X509Certificate> certificates = new ArrayList<>();
            for (java.security.cert.Certificate certificate : factory.generateCertificates(
                    new ByteArrayInputStream(pem.getBytes(StandardCharsets.UTF_8)))) {
                certificates.add((X509Certificate) certificate);
            }
            return certificates;
        } catch (Exception error) {
            throw new IllegalArgumentException("cannot parse PEM certificates", error);
        }
    }
}
