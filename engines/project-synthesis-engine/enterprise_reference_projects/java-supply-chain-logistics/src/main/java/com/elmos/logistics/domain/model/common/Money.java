package com.elmos.logistics.domain.model.common;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

/**
 * Immutable monetary amount representation in minor currency units (cents).
 */
public final class Money implements Comparable<Money> {
    private final long cents;
    private final String currency;

    public Money(long cents, String currency) {
        Objects.requireNonNull(currency, "Currency must not be null");
        this.cents = cents;
        this.currency = currency.toUpperCase();
    }

    public static Money ofCents(long cents, String currency) {
        return new Money(cents, currency);
    }

    public static Money ofMajor(BigDecimal amount, String currency) {
        Objects.requireNonNull(amount, "Amount must not be null");
        long cents = amount.multiply(BigDecimal.valueOf(100))
                .setScale(0, RoundingMode.HALF_UP)
                .longValueExact();
        return new Money(cents, currency);
    }

    public static Money zero(String currency) {
        return new Money(0, currency);
    }

    public long getCents() {
        return cents;
    }

    public String getCurrency() {
        return currency;
    }

    public BigDecimal toMajorUnits() {
        return BigDecimal.valueOf(cents, 2);
    }

    public Money add(Money other) {
        validateSameCurrency(other);
        return new Money(Math.addExact(this.cents, other.cents), currency);
    }

    public Money subtract(Money other) {
        validateSameCurrency(other);
        return new Money(Math.subtractExact(this.cents, other.cents), currency);
    }

    public Money multiply(long factor) {
        return new Money(Math.multiplyExact(this.cents, factor), currency);
    }

    private void validateSameCurrency(Money other) {
        Objects.requireNonNull(other, "Money must not be null");
        if (!this.currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch: " + this.currency + " vs " + other.currency);
        }
    }

    @Override
    public int compareTo(Money o) {
        validateSameCurrency(o);
        return Long.compare(this.cents, o.cents);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Money money = (Money) o;
        return cents == money.cents && Objects.equals(currency, money.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(cents, currency);
    }

    @Override
    public String toString() {
        return String.format("%s %.2f", currency, toMajorUnits());
    }
}
