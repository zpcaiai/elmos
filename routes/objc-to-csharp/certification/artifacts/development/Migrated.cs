public static class Migrated
{
    public static long elmos_fn_ab0aa94ba729d29a(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return checked(subtotal + tax);
    }
}
