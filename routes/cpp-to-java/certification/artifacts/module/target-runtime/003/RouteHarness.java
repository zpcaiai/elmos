public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = Migrated.clampNumber(-10.5d, 0.0d, 100.0d);
        var expected0 = 0.0d;
        if (!((Double.isNaN(actual0) && Double.isNaN(expected0)) || Double.doubleToRawLongBits(actual0) == Double.doubleToRawLongBits(expected0))) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\tfp64-hex\t" + String.format(java.util.Locale.ROOT, "%016x", Double.doubleToRawLongBits(actual0)));
        var actual1 = Migrated.clampNumber(55.25d, 0.0d, 100.0d);
        var expected1 = 55.25d;
        if (!((Double.isNaN(actual1) && Double.isNaN(expected1)) || Double.doubleToRawLongBits(actual1) == Double.doubleToRawLongBits(expected1))) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\tfp64-hex\t" + String.format(java.util.Locale.ROOT, "%016x", Double.doubleToRawLongBits(actual1)));
        var actual2 = Migrated.clampNumber(101.5d, 0.0d, 100.0d);
        var expected2 = 100.0d;
        if (!((Double.isNaN(actual2) && Double.isNaN(expected2)) || Double.doubleToRawLongBits(actual2) == Double.doubleToRawLongBits(expected2))) throw new AssertionError("case 2");
        System.out.println("ELMOS_OBSERVATION\t2\tfp64-hex\t" + String.format(java.util.Locale.ROOT, "%016x", Double.doubleToRawLongBits(actual2)));
        var actual3 = Migrated.clampNumber(-0.0d, -1.0d, 1.0d);
        var expected3 = -0.0d;
        if (!((Double.isNaN(actual3) && Double.isNaN(expected3)) || Double.doubleToRawLongBits(actual3) == Double.doubleToRawLongBits(expected3))) throw new AssertionError("case 3");
        System.out.println("ELMOS_OBSERVATION\t3\tfp64-hex\t" + String.format(java.util.Locale.ROOT, "%016x", Double.doubleToRawLongBits(actual3)));
        var actual4 = Migrated.clampNumber(0.0d, -0.0d, 1.0d);
        var expected4 = 0.0d;
        if (!((Double.isNaN(actual4) && Double.isNaN(expected4)) || Double.doubleToRawLongBits(actual4) == Double.doubleToRawLongBits(expected4))) throw new AssertionError("case 4");
        System.out.println("ELMOS_OBSERVATION\t4\tfp64-hex\t" + String.format(java.util.Locale.ROOT, "%016x", Double.doubleToRawLongBits(actual4)));
    }
}
