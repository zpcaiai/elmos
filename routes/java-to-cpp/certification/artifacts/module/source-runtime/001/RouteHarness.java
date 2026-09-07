public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = EquivalenceModule.calculate(100, 20);
        var expected0 = 120;
        if (actual0 != expected0) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\ti64-dec\t" + Long.toString(actual0));
        var actual1 = EquivalenceModule.calculate(-1, 20);
        var expected1 = 0;
        if (actual1 != expected1) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\ti64-dec\t" + Long.toString(actual1));
        var actual2 = EquivalenceModule.calculate(0, 0);
        var expected2 = 0;
        if (actual2 != expected2) throw new AssertionError("case 2");
        System.out.println("ELMOS_OBSERVATION\t2\ti64-dec\t" + Long.toString(actual2));
        var actual3 = EquivalenceModule.calculate(9223372036854775700L, 7);
        var expected3 = 9223372036854775707L;
        if (actual3 != expected3) throw new AssertionError("case 3");
        System.out.println("ELMOS_OBSERVATION\t3\ti64-dec\t" + Long.toString(actual3));
    }
}
