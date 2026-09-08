public static class Migrated
{
    public static long elmos_fn_882e2a36835781b8(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return checked(subtotal + tax);
    }
}
