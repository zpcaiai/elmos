public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = EquivalenceModule.clamp(-10, 0, 100);
        var expected0 = 0;
        if (actual0 != expected0) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\ti64-dec\t" + Long.toString(actual0));
        var actual1 = EquivalenceModule.clamp(55, 0, 100);
        var expected1 = 55;
        if (actual1 != expected1) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\ti64-dec\t" + Long.toString(actual1));
        var actual2 = EquivalenceModule.clamp(101, 0, 100);
        var expected2 = 100;
        if (actual2 != expected2) throw new AssertionError("case 2");
        System.out.println("ELMOS_OBSERVATION\t2\ti64-dec\t" + Long.toString(actual2));
        var actual3 = EquivalenceModule.clamp(0, 0, 100);
        var expected3 = 0;
        if (actual3 != expected3) throw new AssertionError("case 3");
        System.out.println("ELMOS_OBSERVATION\t3\ti64-dec\t" + Long.toString(actual3));
        var actual4 = EquivalenceModule.clamp(100, 0, 100);
        var expected4 = 100;
        if (actual4 != expected4) throw new AssertionError("case 4");
        System.out.println("ELMOS_OBSERVATION\t4\ti64-dec\t" + Long.toString(actual4));
    }
}
