package io.elmos.verification;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

import static io.elmos.verification.VerificationModels.*;

public final class NumericVerificationEngine {
    public TechniqueResult verifyDecimal(String propertyId,List<BigDecimal> inputs,
                                         Function<BigDecimal,BigDecimal> reference,
                                         Function<BigDecimal,BigDecimal> target,
                                         int scale,RoundingMode rounding,BigDecimal tolerance) {
        if (inputs.isEmpty() || scale<0 || tolerance.signum()<0) throw new IllegalArgumentException("numeric corpus, scale and tolerance are required");
        List<Counterexample> failures=new ArrayList<>(); int executed=0;
        for (BigDecimal input:inputs) {
            BigDecimal expected=reference.apply(input).setScale(scale,rounding);
            BigDecimal observed=target.apply(input).setScale(scale,rounding); executed++;
            BigDecimal error=expected.subtract(observed).abs();
            if (error.compareTo(tolerance)>0) {
                String witness="input="+input.toPlainString()+",expected="+expected.toPlainString()+",observed="+observed.toPlainString()+",error="+error.toPlainString();
                failures.add(CounterexampleFactory.create("numeric",propertyId,0,witness,witness,"TOLERANCE_EXCEEDED")); break;
            }
        }
        return new TechniqueResult("numeric",propertyId,failures.isEmpty()?Status.PASS:Status.FAIL,executed,
                executed/(double)inputs.size(),failures,List.of(),List.of("local://numeric/"+propertyId),
                Map.of("scale",scale,"cases",executed));
    }

    public TechniqueResult verifyIntegerAdditionNoOverflow(String propertyId,List<Long> left,List<Long> right) {
        if (left.size()!=right.size() || left.isEmpty()) throw new IllegalArgumentException("paired integer corpus is required");
        List<Counterexample> failures=new ArrayList<>(); int executed=0;
        for (int index=0;index<left.size();index++) {
            executed++;
            try { Math.addExact(left.get(index),right.get(index)); }
            catch (ArithmeticException error) {
                String witness=left.get(index)+"+"+right.get(index);
                failures.add(CounterexampleFactory.create("numeric",propertyId,0,witness,witness,"INTEGER_OVERFLOW")); break;
            }
        }
        return new TechniqueResult("numeric",propertyId,failures.isEmpty()?Status.PASS:Status.FAIL,executed,
                executed/(double)left.size(),failures,List.of(),List.of("local://numeric/"+propertyId),Map.of("cases",executed));
    }
}
