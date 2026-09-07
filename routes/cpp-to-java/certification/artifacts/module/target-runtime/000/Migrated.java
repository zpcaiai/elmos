public final class Migrated {
    public static boolean elmos_fn_fda5aa27b3c743b7(boolean left, boolean right) {
        return (left && right);
    }

    public static long elmos_fn_9d7517398504726c(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return Math.addExact(subtotal, tax);
    }

    public static long elmos_fn_5d67eed5ad387c44(long value, long minimum, long maximum) {
        if ((value < minimum)) {
            return minimum;
        }
        if ((value > maximum)) {
            return maximum;
        }
        return value;
    }

    public static double elmos_fn_bff0c05627800fbb(double value, double minimum, double maximum) {
        if ((value < minimum)) {
            return minimum;
        }
        if ((value > maximum)) {
            return maximum;
        }
        return value;
    }

    public static long elmos_fn_8ea85b618b85973a(long left, long right) {
        return Math.subtractExact(left, right);
    }
}
