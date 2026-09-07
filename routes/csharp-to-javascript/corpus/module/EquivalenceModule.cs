public static class EquivalenceModule
{
    public static long calculate(long subtotal, long tax)
    {
        if (subtotal < 0) { return 0; }
        return subtotal + tax;
    }

    public static long clamp(long value, long minimum, long maximum)
    {
        if (value < minimum) { return minimum; }
        if (value > maximum) { return maximum; }
        return value;
    }

    public static long difference(long left, long right) => left - right;

    public static double clampNumber(double value, double minimum, double maximum)
    {
        if (value < minimum) { return minimum; }
        if (value > maximum) { return maximum; }
        return value;
    }

    public static bool both(bool left, bool right) => left && right;
}
