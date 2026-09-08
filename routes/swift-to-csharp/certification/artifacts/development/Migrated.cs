public static class Migrated
{
    public static long elmos_fn_8e6345c6b301051b(long subtotal, long tax) {
        if ((subtotal < 0)) {
            return 0;
        }
        return checked(subtotal + tax);
    }
}
