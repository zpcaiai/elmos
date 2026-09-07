public class Records2 {
    // A compact constructor validates and may *reassign* the components; the
    // field is written from whatever the parameter holds afterwards.
    record Clamped(int lo, int hi) {
        Clamped {
            if (lo > hi) { throw new IllegalArgumentException("lo>hi"); }
            lo = lo * 2;
            hi = hi + lo;
        }
        int span() { return hi - lo; }
    }

    // An explicit canonical constructor assigns the fields itself.
    record Shifted(int a, int b) {
        Shifted(int a, int b) {
            this.a = a + 1;
            this.b = b * 3;
        }
    }

    record Empty() {
        Empty {
            System.out.println("empty-built");
        }
    }

    static int arrow(int n) {
        return switch (n % 3) {
            case 0 -> 10;
            case 1, 2 -> 20;
            default -> 30;
        };
    }

    static String yielded(int n) {
        return switch (n % 2) {
            case 1: yield "odd";
            default: yield "even";
        };
    }

    // An arrow switch *statement* cannot fall through.
    static int arrowStatement(int n) {
        int t = 0;
        switch (n % 3) {
            case 0 -> t = 1;
            case 1 -> t = 2;
            default -> t = 3;
        }
        return t;
    }

    // The subject must be evaluated exactly once, even with side effects.
    static int calls = 0;
    static int bump(int n) { calls = calls + 1; return n % 2; }

    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        Clamped c = new Clamped(a, a + 5);
        System.out.println("clamped=" + c.lo() + "," + c.hi() + "," + c.span());
        System.out.println("clampedStr=" + c);
        Shifted s = new Shifted(a, a);
        System.out.println("shifted=" + s.a() + "," + s.b());
        System.out.println("eq=" + s.equals(new Shifted(a, a)));
        Empty e = new Empty();
        System.out.println("emptyStr=" + e);
        System.out.println("arrow=" + arrow(a));
        System.out.println("yield=" + yielded(a));
        System.out.println("arrowStmt=" + arrowStatement(a));
        int r = switch (bump(a)) {
            case 0 -> 100;
            default -> 200;
        };
        System.out.println("once=" + r + " calls=" + calls);
    }
}
