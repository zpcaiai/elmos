public static class Migrated
{
    public static long elmos_fn_6ccc133738e9ecaf(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return checked(subtotal + tax);
    }
}
