public final class Migrated {
    public static double calculate(double subtotal, double tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return (subtotal + tax);
    }
}
