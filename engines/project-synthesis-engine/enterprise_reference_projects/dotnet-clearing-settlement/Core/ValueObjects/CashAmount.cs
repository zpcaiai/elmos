namespace Elmos.ClearingSettlement.Core.ValueObjects;

using System;
using System.Globalization;

/// <summary>
/// Immutable high-precision cash amount with currency enforcement and operator overloading.
/// Internally stored in minor currency units (cents/basis points) as a signed 64-bit integer.
/// </summary>
public readonly struct CashAmount : IEquatable<CashAmount>, IComparable<CashAmount>
{
    public long MinorUnits { get; }
    public Currency Currency { get; }

    public CashAmount(long minorUnits, Currency currency)
    {
        MinorUnits = minorUnits;
        Currency = currency;
    }

    public static CashAmount Of(long minorUnits, Currency currency) => new(minorUnits, currency);

    public static CashAmount FromDecimal(decimal amount, Currency currency)
    {
        long factor = (long)Math.Pow(10, currency.DecimalPlaces);
        long units = (long)Math.Round(amount * factor, MidpointRounding.AwayFromZero);
        return new CashAmount(units, currency);
    }

    public static CashAmount Zero(Currency currency) => new(0, currency);

    public decimal ToDecimal()
    {
        long factor = (long)Math.Pow(10, Currency.DecimalPlaces);
        return (decimal)MinorUnits / factor;
    }

    public CashAmount Abs() => new(Math.Abs(MinorUnits), Currency);

    public bool IsPositive => MinorUnits > 0;
    public bool IsNegative => MinorUnits < 0;
    public bool IsZero => MinorUnits == 0;

    public CashAmount Add(CashAmount other)
    {
        EnsureSameCurrency(other);
        return new CashAmount(checked(MinorUnits + other.MinorUnits), Currency);
    }

    public CashAmount Subtract(CashAmount other)
    {
        EnsureSameCurrency(other);
        return new CashAmount(checked(MinorUnits - other.MinorUnits), Currency);
    }

    public CashAmount Multiply(decimal factor)
    {
        long resultUnits = (long)Math.Round(MinorUnits * factor, MidpointRounding.AwayFromZero);
        return new CashAmount(resultUnits, Currency);
    }

    private void EnsureSameCurrency(CashAmount other)
    {
        if (Currency != other.Currency)
            throw new InvalidOperationException($"Cannot operate on mismatched currencies: {Currency} and {other.Currency}");
    }

    public static CashAmount operator +(CashAmount a, CashAmount b) => a.Add(b);
    public static CashAmount operator -(CashAmount a, CashAmount b) => a.Subtract(b);
    public static CashAmount operator -(CashAmount a) => new(-a.MinorUnits, a.Currency);
    public static CashAmount operator *(CashAmount a, decimal factor) => a.Multiply(factor);
    public static CashAmount operator *(decimal factor, CashAmount a) => a.Multiply(factor);

    public static bool operator >(CashAmount a, CashAmount b)
    {
        a.EnsureSameCurrency(b);
        return a.MinorUnits > b.MinorUnits;
    }

    public static bool operator <(CashAmount a, CashAmount b)
    {
        a.EnsureSameCurrency(b);
        return a.MinorUnits < b.MinorUnits;
    }

    public static bool operator >=(CashAmount a, CashAmount b)
    {
        a.EnsureSameCurrency(b);
        return a.MinorUnits >= b.MinorUnits;
    }

    public static bool operator <=(CashAmount a, CashAmount b)
    {
        a.EnsureSameCurrency(b);
        return a.MinorUnits <= b.MinorUnits;
    }

    public bool Equals(CashAmount other) => MinorUnits == other.MinorUnits && Currency == other.Currency;

    public override bool Equals(object? obj) => obj is CashAmount other && Equals(other);

    public override int GetHashCode() => HashCode.Combine(MinorUnits, Currency);

    public int CompareTo(CashAmount other)
    {
        EnsureSameCurrency(other);
        return MinorUnits.CompareTo(other.MinorUnits);
    }

    public static bool operator ==(CashAmount left, CashAmount right) => left.Equals(right);
    public static bool operator !=(CashAmount left, CashAmount right) => !left.Equals(right);

    public override string ToString() => string.Format(CultureInfo.InvariantCulture, "{0} {1:F2}", Currency.Code, ToDecimal());
}
