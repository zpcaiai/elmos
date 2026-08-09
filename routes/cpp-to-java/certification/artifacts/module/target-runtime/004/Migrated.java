public final class Migrated {
    public static boolean both(boolean left, boolean right) {
        return (left && right);
    }

    public static long calculate(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return Math.addExact(subtotal, tax);
    }

    public static long clamp(long value, long minimum, long maximum) {
        if ((value < minimum)) {
            return minimum;
        }
        if ((value > maximum)) {
            return maximum;
        }
        return value;
    }

    public static double clampNumber(double value, double minimum, double maximum) {
        if ((value < minimum)) {
            return minimum;
        }
        if ((value > maximum)) {
            return maximum;
        }
        return value;
    }

    public static long difference(long left, long right) {
        return Math.subtractExact(left, right);
    }
}
