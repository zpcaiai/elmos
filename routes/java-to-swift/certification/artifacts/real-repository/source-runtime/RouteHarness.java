public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = Difference.difference(20, 7);
        var expected0 = 13;
        if (actual0 != expected0) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\ti64-dec\t" + Long.toString(actual0));
        var actual1 = Difference.difference(3, 8);
        var expected1 = 0;
        if (actual1 != expected1) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\ti64-dec\t" + Long.toString(actual1));
        var actual2 = Difference.difference(4, 4);
        var expected2 = 0;
        if (actual2 != expected2) throw new AssertionError("case 2");
        System.out.println("ELMOS_OBSERVATION\t2\ti64-dec\t" + Long.toString(actual2));
    }
}
