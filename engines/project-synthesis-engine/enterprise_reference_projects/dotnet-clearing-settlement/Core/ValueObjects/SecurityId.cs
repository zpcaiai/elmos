namespace Elmos.ClearingSettlement.Core.ValueObjects;

using System;
using System.Text;
using System.Text.RegularExpressions;

/// <summary>
/// International Securities Identification Number (ISIN) conforming to ISO 6166.
/// Implements full Double-Add-Double / Luhn Modulo 10 checksum validation.
/// </summary>
public readonly struct SecurityId : IEquatable<SecurityId>, IComparable<SecurityId>
{
    private static readonly Regex IsinRegex = new("^[A-Z]{2}[A-Z0-9]{9}[0-9]$", RegexOptions.Compiled);

    public string Value { get; }
    public string CountryCode => Value[..2];
    public string Nsin => Value.Substring(2, 9);
    public int CheckDigit => Value[^1] - '0';

    public SecurityId(string isin)
    {
        if (string.IsNullOrWhiteSpace(isin))
            throw new ArgumentException("ISIN cannot be null or whitespace", nameof(isin));

        string upper = isin.Trim().ToUpperInvariant();
        if (!IsinRegex.IsMatch(upper))
            throw new ArgumentException($"Invalid ISIN format: '{isin}'. Must match 2 letters, 9 alphanumeric, 1 digit.", nameof(isin));

        if (!ValidateLuhnChecksum(upper))
            throw new ArgumentException($"ISIN '{isin}' failed ISO 6166 Luhn modulo-10 checksum validation.", nameof(isin));

        Value = upper;
    }

    public static SecurityId Parse(string isin) => new(isin);

    public static bool TryParse(string? isin, out SecurityId result)
    {
        if (string.IsNullOrWhiteSpace(isin) || !IsinRegex.IsMatch(isin.Trim().ToUpperInvariant()))
        {
            result = default;
            return false;
        }

        string upper = isin.Trim().ToUpperInvariant();
        if (!ValidateLuhnChecksum(upper))
        {
            result = default;
            return false;
        }

        result = new SecurityId(upper);
        return true;
    }

    /// <summary>
    /// Validates ISIN using ISO 6166 check digit algorithm:
    /// 1. Letters converted to numbers (A=10, B=11 ... Z=35).
    /// 2. Double every second digit from right to left.
    /// 3. Add digits. Sum mod 10 == 0.
    /// </summary>
    private static bool ValidateLuhnChecksum(string isin)
    {
        var sb = new StringBuilder();
        foreach (char c in isin)
        {
            if (char.IsLetter(c))
                sb.Append(c - 'A' + 10);
            else
                sb.Append(c);
        }

        string digits = sb.ToString();
        int sum = 0;
        bool doubleIt = true; // start doubling from the second digit from the right

        for (int i = digits.Length - 2; i >= 0; i--)
        {
            int d = digits[i] - '0';
            if (doubleIt)
            {
                d *= 2;
                if (d > 9) d = (d / 10) + (d % 10);
            }
            sum += d;
            doubleIt = !doubleIt;
        }

        int calculatedCheckDigit = (10 - (sum % 10)) % 10;
        int actualCheckDigit = digits[^1] - '0';
        return calculatedCheckDigit == actualCheckDigit;
    }

    public bool Equals(SecurityId other) => string.Equals(Value, other.Value, StringComparison.OrdinalIgnoreCase);

    public override bool Equals(object? obj) => obj is SecurityId other && Equals(other);

    public override int GetHashCode() => StringComparer.OrdinalIgnoreCase.GetHashCode(Value);

    public int CompareTo(SecurityId other) => string.Compare(Value, other.Value, StringComparison.OrdinalIgnoreCase);

    public static bool operator ==(SecurityId left, SecurityId right) => left.Equals(right);
    public static bool operator !=(SecurityId left, SecurityId right) => !left.Equals(right);

    public override string ToString() => Value;
}
