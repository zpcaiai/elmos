public final class Migrated {
    public static long clamp(long value, long upper) {
        if ((value > upper)) {
            return upper;
        }
        if ((value < 0)) {
            return 0;
        }
        return value;
    }
}
