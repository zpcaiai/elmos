public static class Migrated
{
    public static long elmos_fn_7f435b0fbfc36ee2(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return checked(subtotal + tax);
    }
}
