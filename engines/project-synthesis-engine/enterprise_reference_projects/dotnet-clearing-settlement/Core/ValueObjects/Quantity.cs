namespace Elmos.ClearingSettlement.Core.ValueObjects;

using System;

/// <summary>
/// Security shares or contract quantity representation with signed directional support.
/// Positive = Long / Buyer delivery obligation.
/// Negative = Short / Seller delivery obligation.
/// </summary>
public readonly struct Quantity : IEquatable<Quantity>, IComparable<Quantity>
{
    public long Units { get; }

    public Quantity(long units)
    {
        Units = units;
    }

    public static Quantity Of(long units) => new(units);
    public static Quantity Zero => new(0);

    public Quantity Abs() => new(Math.Abs(Units));
    public bool IsZero => Units == 0;
    public bool IsPositive => Units > 0;
    public bool IsNegative => Units < 0;

    public Quantity Add(Quantity other) => new(checked(Units + other.Units));
    public Quantity Subtract(Quantity other) => new(checked(Units - other.Units));

    public static Quantity operator +(Quantity a, Quantity b) => a.Add(b);
    public static Quantity operator -(Quantity a, Quantity b) => a.Subtract(b);
    public static Quantity operator -(Quantity a) => new(-a.Units);

    public static bool operator >(Quantity a, Quantity b) => a.Units > b.Units;
    public static bool operator <(Quantity a, Quantity b) => a.Units < b.Units;
    public static bool operator >=(Quantity a, Quantity b) => a.Units >= b.Units;
    public static bool operator <=(Quantity a, Quantity b) => a.Units <= b.Units;

    public bool Equals(Quantity other) => Units == other.Units;
    public override bool Equals(object? obj) => obj is Quantity other && Equals(other);
    public override int GetHashCode() => Units.GetHashCode();
    public int CompareTo(Quantity other) => Units.CompareTo(other.Units);

    public static bool operator ==(Quantity left, Quantity right) => left.Equals(right);
    public static bool operator !=(Quantity left, Quantity right) => !left.Equals(right);

    public override string ToString() => Units.ToString("N0");
}
