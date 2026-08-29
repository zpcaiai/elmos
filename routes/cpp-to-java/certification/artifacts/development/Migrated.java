public final class Migrated {
    public static long elmos_fn_b80b5f72c2df9f87(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return Math.addExact(subtotal, tax);
    }
}
