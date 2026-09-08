public final class Migrated {
    public static long elmos_fn_96f412b173215a68(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return Math.addExact(subtotal, tax);
    }
}
