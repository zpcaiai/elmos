public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = Migrated.clamp(20, 10);
        if (actual0 != 10) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\tb64\t" + java.util.Base64.getEncoder().encodeToString(String.valueOf(actual0).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        var actual1 = Migrated.clamp(-2, 10);
        if (actual1 != 0) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\tb64\t" + java.util.Base64.getEncoder().encodeToString(String.valueOf(actual1).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        var actual2 = Migrated.clamp(7, 10);
        if (actual2 != 7) throw new AssertionError("case 2");
        System.out.println("ELMOS_OBSERVATION\t2\tb64\t" + java.util.Base64.getEncoder().encodeToString(String.valueOf(actual2).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    }
}
