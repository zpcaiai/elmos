package io.elmos.legacy.web;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Positive;

public class LegacyOrderForm {
    @NotBlank
    private String customerId;

    @Positive
    private long amountCents;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public long getAmountCents() {
        return amountCents;
    }

    public void setAmountCents(long amountCents) {
        this.amountCents = amountCents;
    }
}
