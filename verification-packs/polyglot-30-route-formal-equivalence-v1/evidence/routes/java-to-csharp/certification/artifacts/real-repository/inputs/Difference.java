public final class Difference {
    private Difference() {}

    public static long difference(long left, long right) {
        if (left < right) {
            return 0;
        }
        return left - right;
    }
}
