public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = Decision.decision(true, true, false);
        var expected0 = true;
        if (actual0 != expected0) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\tbool\t" + Boolean.toString(actual0));
        var actual1 = Decision.decision(true, false, false);
        var expected1 = false;
        if (actual1 != expected1) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\tbool\t" + Boolean.toString(actual1));
        var actual2 = Decision.decision(false, false, true);
        var expected2 = true;
        if (actual2 != expected2) throw new AssertionError("case 2");
        System.out.println("ELMOS_OBSERVATION\t2\tbool\t" + Boolean.toString(actual2));
        var actual3 = Decision.decision(false, false, false);
        var expected3 = false;
        if (actual3 != expected3) throw new AssertionError("case 3");
        System.out.println("ELMOS_OBSERVATION\t3\tbool\t" + Boolean.toString(actual3));
    }
}
