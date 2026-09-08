public final class Migrated {
    public static long elmos_fn_79ec1fad99837217(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return Math.addExact(subtotal, tax);
    }
}
