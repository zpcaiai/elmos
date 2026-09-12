namespace Elmos.ClearingSettlement.Core.ValueObjects;

using System;
using System.Collections.Generic;

/// <summary>
/// ISO-4217 standard currency representation with minor-unit decimals.
/// </summary>
public readonly struct Currency : IEquatable<Currency>, IComparable<Currency>
{
    public static readonly Currency USD = new("USD", 840, 2, "$");
    public static readonly Currency EUR = new("EUR", 978, 2, "€");
    public static readonly Currency GBP = new("GBP", 826, 2, "£");
    public static readonly Currency JPY = new("JPY", 392, 0, "¥");
    public static readonly Currency CHF = new("CHF", 756, 2, "CHF");
    public static readonly Currency CAD = new("CAD", 124, 2, "CA$");
    public static readonly Currency HKD = new("HKD", 344, 2, "HK$");

    public string Code { get; }
    public int NumericCode { get; }
    public int DecimalPlaces { get; }
    public string Symbol { get; }

    public Currency(string code, int numericCode, int decimalPlaces, string symbol)
    {
        if (string.IsNullOrWhiteSpace(code) || code.Length != 3)
            throw new ArgumentException("Currency code must be exactly 3 uppercase characters", nameof(code));

        Code = code.ToUpperInvariant();
        NumericCode = numericCode;
        DecimalPlaces = decimalPlaces;
        Symbol = symbol ?? Code;
    }

    public static Currency FromCode(string code)
    {
        return code?.ToUpperInvariant() switch
        {
            "USD" => USD,
            "EUR" => EUR,
            "GBP" => GBP,
            "JPY" => JPY,
            "CHF" => CHF,
            "CAD" => CAD,
            "HKD" => HKD,
            _ => new Currency(code ?? throw new ArgumentNullException(nameof(code)), 0, 2, code)
        };
    }

    public bool Equals(Currency other) => string.Equals(Code, other.Code, StringComparison.OrdinalIgnoreCase);

    public override bool Equals(object? obj) => obj is Currency other && Equals(other);

    public override int GetHashCode() => StringComparer.OrdinalIgnoreCase.GetHashCode(Code);

    public int CompareTo(Currency other) => string.Compare(Code, other.Code, StringComparison.OrdinalIgnoreCase);

    public static bool operator ==(Currency left, Currency right) => left.Equals(right);
    public static bool operator !=(Currency left, Currency right) => !left.Equals(right);

    public override string ToString() => Code;
}
