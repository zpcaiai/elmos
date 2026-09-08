public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = Migrated.elmos_fn_d7f4315f9912b613(20, 10);
        var expected0 = 10;
        if (actual0 != expected0) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\ti64-dec\t" + Long.toString(actual0));
        var actual1 = Migrated.elmos_fn_d7f4315f9912b613(-2, 10);
        var expected1 = 0;
        if (actual1 != expected1) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\ti64-dec\t" + Long.toString(actual1));
        var actual2 = Migrated.elmos_fn_d7f4315f9912b613(7, 10);
        var expected2 = 7;
        if (actual2 != expected2) throw new AssertionError("case 2");
        System.out.println("ELMOS_OBSERVATION\t2\ti64-dec\t" + Long.toString(actual2));
    }
}
