public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = Migrated.elmos_fn_80e069bf200ec120(2, 3);
        var expected0 = 5;
        if (actual0 != expected0) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\ti64-dec\t" + Long.toString(actual0));
        var actual1 = Migrated.elmos_fn_80e069bf200ec120(-4, 1);
        var expected1 = -3;
        if (actual1 != expected1) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\ti64-dec\t" + Long.toString(actual1));
    }
}
