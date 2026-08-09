public final class RouteHarness {
    public static void main(String[] args) {
        var actual0 = Pricing.calculate(100, 20);
        if (actual0 != 120) throw new AssertionError("case 0");
        System.out.println("ELMOS_OBSERVATION\t0\tb64\t" + java.util.Base64.getEncoder().encodeToString(String.valueOf(actual0).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        var actual1 = Pricing.calculate(-1, 5);
        if (actual1 != 0) throw new AssertionError("case 1");
        System.out.println("ELMOS_OBSERVATION\t1\tb64\t" + java.util.Base64.getEncoder().encodeToString(String.valueOf(actual1).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        var actual2 = Pricing.calculate(7, -2);
        if (actual2 != 5) throw new AssertionError("case 2");
        System.out.println("ELMOS_OBSERVATION\t2\tb64\t" + java.util.Base64.getEncoder().encodeToString(String.valueOf(actual2).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    }
}
