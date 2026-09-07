public final class Pricing {
    public static long calculate(long subtotal, long tax) {
        if (subtotal < 0) { return 0; }
        return subtotal + tax;
    }
}
