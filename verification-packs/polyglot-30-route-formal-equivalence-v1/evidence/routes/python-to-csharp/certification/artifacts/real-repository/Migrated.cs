public static class Migrated
{
    public static long difference(long left, long right) {
        if ((left < right)) {
            return 0;
        }
        return checked(left - right);
    }
}
