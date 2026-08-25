public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = Migrated.elmos_fn_0bb126c58397bbee(3, 4);
        var expected0 = 12;
        if (actual0 != expected0) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\ti64-dec\t" + Long.toString(actual0));
        var actual1 = Migrated.elmos_fn_0bb126c58397bbee(-2, 5);
        var expected1 = -10;
        if (actual1 != expected1) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\ti64-dec\t" + Long.toString(actual1));
    }
}
