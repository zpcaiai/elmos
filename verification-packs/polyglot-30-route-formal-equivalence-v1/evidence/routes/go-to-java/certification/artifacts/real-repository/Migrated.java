public final class Migrated {
    public static long difference(long left, long right) {
        if ((left < right)) {
            return 0;
        }
        return Math.subtractExact(left, right);
    }
}
