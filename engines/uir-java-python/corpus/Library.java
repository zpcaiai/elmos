import java.util.List;
import java.util.Objects;

public class Library {
    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        String s = args[1];

        // ---- String -------------------------------------------------------
        System.out.println("blank=" + s.isBlank() + "," + "".isBlank() + "," + "  \t ".isBlank());
        System.out.println("strip=[" + ("  " + s + " \t").strip() + "]");
        System.out.println("starts=" + s.startsWith("a") + " ends=" + s.endsWith("c"));
        System.out.println("contains=" + s.contains("b"));
        System.out.println("replace=" + s.replace("a", "Z"));
        System.out.println("last=" + s.lastIndexOf("a"));
        System.out.println("repeat=" + s.repeat(2));
        System.out.println("concat=" + s.concat("!"));
        System.out.println("ignore=" + s.equalsIgnoreCase("ABC"));
        // compareTo returns the char difference, not just its sign.
        System.out.println("cmp=" + s.compareTo("abc") + "," + "a".compareTo("A"));
        // hashCode is 31-based and wraps at 32 bits.
        System.out.println("hash=" + s.hashCode() + "," + "hello".hashCode());
        // split drops trailing empty strings.
        String[] parts = "a,b,,".split(",");
        System.out.println("splitLen=" + parts.length + " first=" + parts[0]);
        String[] one = "no-separator".split(",");
        System.out.println("splitOne=" + one.length);

        // ---- Objects ------------------------------------------------------
        System.out.println("nonNull=" + Objects.nonNull(s) + " isNull=" + Objects.isNull(null));
        System.out.println("objEq=" + Objects.equals(s, "abc") + "," + Objects.equals(null, null));
        System.out.println("objStr=" + Objects.toString(null, "fallback"));
        System.out.println("objHash=" + Objects.hash(1, 2, 3));
        System.out.println("req=" + Objects.requireNonNull(s));

        // ---- Math ---------------------------------------------------------
        // Math.round is floor(x+0.5); Python's round() does banker's rounding.
        System.out.println("round=" + Math.round(2.5) + "," + Math.round(-2.5)
                + "," + Math.round(0.5) + "," + Math.round(1.5) + "," + Math.round(-0.5));
        System.out.println("floorDiv=" + Math.floorDiv(a, 3) + " floorMod=" + Math.floorMod(a, 3));
        System.out.println("signum=" + Math.signum((double) a));
        System.out.println("hypot=" + Math.hypot(3.0, 4.0));

        // ---- Integer ------------------------------------------------------
        System.out.println("hex=" + Integer.toHexString(a) + "," + Integer.toHexString(-1));
        System.out.println("bin=" + Integer.toBinaryString(a));
        System.out.println("bits=" + Integer.bitCount(a));
        System.out.println("isum=" + Integer.sum(a, 1) + " imax=" + Integer.max(a, 0));

        // ---- List ---------------------------------------------------------
        List<Integer> fixed = List.of(1, 2, 3);
        System.out.println("listSize=" + fixed.size() + " get=" + fixed.get(1)
                + " has=" + fixed.contains(2) + " idx=" + fixed.indexOf(3));
        System.out.println("listStr=" + fixed);
        java.util.ArrayList<Integer> grow = new java.util.ArrayList<Integer>();
        grow.add(a);
        grow.add(a + 1);
        System.out.println("growSize=" + grow.size() + " g0=" + grow.get(0) + " str=" + grow);

        // ---- exact arithmetic ---------------------------------------------
        try {
            System.out.println("exact=" + Math.multiplyExact(a, a));
        } catch (ArithmeticException e) {
            System.out.println("exactThrew=" + e.getMessage());
        }
        try {
            System.out.println("add=" + Math.addExact(a, Integer.MAX_VALUE));
        } catch (ArithmeticException e) {
            System.out.println("addThrew=" + e.getMessage());
        }

        // ---- immutability contract ----------------------------------------
        try {
            fixed.add(4);
            System.out.println("mutated");
        } catch (UnsupportedOperationException e) {
            System.out.println("immutable");
        }

        // ---- out of range ---------------------------------------------------
        try {
            System.out.println(fixed.get(9));
        } catch (IndexOutOfBoundsException e) {
            System.out.println("oob");
        }
        Objects.requireNonNull(s, "must not be null");
        System.out.println("done");
    }
}
