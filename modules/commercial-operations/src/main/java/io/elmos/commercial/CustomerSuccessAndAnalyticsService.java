package io.elmos.commercial;

import io.elmos.commercial.CommercialModels.*;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class CustomerSuccessAndAnalyticsService {

    public CustomerHealth health(CustomerSignals signals) {
        List<String> reasons = new ArrayList<>();
        if (signals.evidenceRefs().isEmpty()) {
            return new CustomerHealth(CustomerHealthStatus.UNKNOWN, BigDecimal.ZERO,
                    List.of("HEALTH_EVIDENCE_MISSING"), List.of(), false, false);
        }
        BigDecimal adoption = signals.adoption();
        if (signals.privateUsageMissing()) {
            reasons.add("PRIVATE_USAGE_MISSING_NOT_ZERO");
            adoption = null;
        }
        if (signals.plannedProjectsComplete()) reasons.add("PLANNED_PROJECTS_COMPLETE");
        if (signals.slaBreachOpen()) reasons.add("OPEN_SLA_BREACH");
        BigDecimal total = signals.deliverySuccess().add(signals.validationQuality()).add(signals.supportHealth());
        int divisor = 3;
        if (adoption != null) { total = total.add(adoption); divisor++; }
        BigDecimal score = total.divide(BigDecimal.valueOf(divisor), 4, RoundingMode.HALF_UP);
        CustomerHealthStatus status;
        if (signals.slaBreachOpen() || score.compareTo(new BigDecimal("0.35")) < 0) status = CustomerHealthStatus.CRITICAL;
        else if (score.compareTo(new BigDecimal("0.55")) < 0) status = CustomerHealthStatus.AT_RISK;
        else if (score.compareTo(new BigDecimal("0.75")) < 0) status = CustomerHealthStatus.WATCH;
        else status = CustomerHealthStatus.HEALTHY;
        if (signals.plannedProjectsComplete() && !signals.slaBreachOpen()
                && signals.deliverySuccess().compareTo(new BigDecimal("0.8")) >= 0
                && status == CustomerHealthStatus.AT_RISK) {
            status = CustomerHealthStatus.WATCH;
            reasons.add("LOW_USAGE_CONTEXT_CORRECTED_BY_SUCCESS_PLAN");
        }
        boolean renewal = signals.daysToRenewal() <= 180;
        boolean expansion = status != CustomerHealthStatus.CRITICAL
                && signals.deliverySuccess().compareTo(new BigDecimal("0.8")) >= 0
                && signals.validationQuality().compareTo(new BigDecimal("0.8")) >= 0;
        reasons.add("WEIGHTED_EVIDENCE_SCORE");
        return new CustomerHealth(status, score, reasons, signals.evidenceRefs(), renewal, expansion);
    }

    public CommercialMetric metric(String key, BigDecimal value, MetricValueStatus status,
                                   String definitionVersion, String source, String timeWindow,
                                   String currency, BigDecimal coverage) {
        CommercialModels.require(key, "metricKey"); CommercialModels.require(definitionVersion, "definitionVersion");
        if (status == MetricValueStatus.MISSING && value != null && value.signum() == 0) {
            throw new IllegalArgumentException("MISSING_METRIC_CANNOT_BE_REPRESENTED_AS_ZERO");
        }
        if (coverage == null || coverage.signum() < 0 || coverage.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("coverage must be between zero and one");
        }
        return new CommercialMetric(key, value, status, definitionVersion, source, timeWindow, currency, coverage);
    }

    public boolean costAnomaly(BigDecimal currentCost, BigDecimal historicalMean, BigDecimal multiplierThreshold) {
        if (historicalMean == null || historicalMean.signum() <= 0) return false;
        return currentCost.divide(historicalMean, 6, RoundingMode.HALF_UP).compareTo(multiplierThreshold) >= 0;
    }

    public ProductizationCandidate productizationCandidate(String fingerprint,
                                                           Map<String, Integer> occurrencesByOrganization,
                                                           BigDecimal engineerCost,
                                                           List<String> evidenceRefs) {
        int organizations = occurrencesByOrganization.size();
        int reuse = occurrencesByOrganization.values().stream().mapToInt(Integer::intValue).sum();
        Set<String> suggestions = organizations >= 5
                ? Set.of("CUSTOM_RECIPE", "VALIDATION_PROFILE", "IMPLEMENTATION_PLAYBOOK") : Set.of();
        return new ProductizationCandidate("candidate-" + Integer.toUnsignedString(fingerprint.hashCode()),
                fingerprint, organizations, reuse, engineerCost, suggestions, evidenceRefs);
    }
}
