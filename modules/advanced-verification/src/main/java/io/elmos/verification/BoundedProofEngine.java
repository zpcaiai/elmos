package io.elmos.verification;

import java.util.List;
import java.util.function.Predicate;

import static io.elmos.verification.VerificationModels.*;

public final class BoundedProofEngine {
    public <T> ProofResult<T> proveFiniteDomain(String propertyId, List<T> declaredCompleteDomain,
                                                Predicate<T> property, int maximumStates,
                                                List<String> assumptions) {
        if (declaredCompleteDomain.isEmpty() || maximumStates<1) throw new IllegalArgumentException("finite domain and state budget are required");
        int explored=0;
        for (T value:declaredCompleteDomain) {
            if (explored>=maximumStates) return new ProofResult<>(propertyId,ProofStatus.UNKNOWN_BUDGET_EXHAUSTED,
                    explored,declaredCompleteDomain.size(),null,assumptions,List.of("local://bounded-proof/"+propertyId));
            explored++;
            if (!property.test(value)) return new ProofResult<>(propertyId,ProofStatus.DISPROVED,explored,
                    declaredCompleteDomain.size(),value,assumptions,List.of("local://bounded-proof/"+propertyId));
        }
        return new ProofResult<>(propertyId,ProofStatus.PROVED_WITHIN_DECLARED_FINITE_DOMAIN,explored,
                declaredCompleteDomain.size(),null,assumptions,List.of("local://bounded-proof/"+propertyId));
    }

    public <T> ProofResult<T> unsupported(String propertyId,String reason) {
        return new ProofResult<>(propertyId,ProofStatus.UNSUPPORTED,0,0,null,List.of(reason),List.of());
    }
}
