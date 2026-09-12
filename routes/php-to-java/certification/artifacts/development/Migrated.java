public final class Migrated {
    public static long elmos_fn_c5658acc3b278ca3(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return Math.addExact(subtotal, tax);
    }
}
