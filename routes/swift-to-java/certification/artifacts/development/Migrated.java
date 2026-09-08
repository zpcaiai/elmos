public final class Migrated {
    public static long elmos_fn_cce2ae594c46403e(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return Math.addExact(subtotal, tax);
    }
}
