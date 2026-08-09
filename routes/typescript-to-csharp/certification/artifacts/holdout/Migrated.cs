public static class Migrated
{
    public static double clamp(double value, double upper) {
        if ((value > upper)) {
            return upper;
        }
        if ((value < 0)) {
            return 0;
        }
        return value;
    }
}
