import java.util.function.Function;
import java.util.function.Supplier;
import java.util.function.Predicate;
import java.util.function.BiFunction;

public class Lambdas {
    interface Marker {}

    interface ToDouble { double of(int x); }

    static int useFn(Function<Integer,Integer> f, int v) { return f.apply(v); }

    static int fold(BiFunction<Integer,Integer,Integer> op, int a, int b) {
        return op.apply(a, b);
    }

    private int base;
    Lambdas(int base) { this.base = base; }
    int scaled(int v) { return base * v; }

    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);

        Function<Integer,Integer> inc = x -> x + 1;
        System.out.println("inc=" + useFn(inc, a));

        // 32-bit wrapping must survive being moved into a lambda.
        Function<Integer,Integer> big = x -> x * 65536 * 65536;
        System.out.println("wrap=" + useFn(big, a));

        // Truncating division and dividend-signed remainder inside a lambda.
        Function<Integer,Integer> half = x -> x / 2;
        Function<Integer,Integer> rem = x -> x % 3;
        System.out.println("half=" + useFn(half, a) + " rem=" + useFn(rem, a));

        int captured = a * 2;
        Supplier<Integer> sup = () -> captured + 1;
        System.out.println("sup=" + sup.get());

        Predicate<Integer> pos = v -> v > 0;
        System.out.println("pos=" + pos.test(a));

        Runnable r = () -> { System.out.println("ran=" + captured); };
        r.run();

        Function<Integer,Integer> blocky = x -> { int t = x * 3; return t - 1; };
        System.out.println("blocky=" + blocky.apply(a));

        System.out.println("fold=" + fold((p, q) -> p - q, a, 7));

        // The lambda's declared result type is Double, so Java widens the int
        // division before returning: 3 / 2 comes back as 1.0, not 1.
        // The interface's result type is double, so Java widens the *int*
        // division on the way out: 3 / 2 comes back as 1.0, not 1.
        ToDouble widen = x -> { return x / 2; };
        System.out.println("widen=" + widen.of(a));
        ToDouble widenExpr = x -> x / 2;
        System.out.println("widenExpr=" + widenExpr.of(a));

        // The capture trap: each lambda must see the value of `v` at the moment
        // it was created.  Python's closures read the variable at call time, so
        // without by-value capture every entry below prints the last value.
        int[] vals = {a, a + 1, a + 2};
        Supplier<Integer>[] made = new Supplier[3];
        int i = 0;
        for (int v : vals) {
            made[i] = () -> v * 10;
            i++;
        }
        System.out.println("cap0=" + made[0].get());
        System.out.println("cap1=" + made[1].get());
        System.out.println("cap2=" + made[2].get());

        // A lambda created inside a loop that also captures a loop-local.
        Function<Integer,Integer>[] adders = new Function[3];
        for (int k = 0; k < 3; k++) {
            int offset = k * 100;
            adders[k] = x -> x + offset;
        }
        System.out.println("add0=" + adders[0].apply(a));
        System.out.println("add1=" + adders[1].apply(a));
        System.out.println("add2=" + adders[2].apply(a));

        // Method references.
        Lambdas self = new Lambdas(a);
        Function<Integer,Integer> bound = self::scaled;
        System.out.println("bound=" + bound.apply(3));
        Function<Integer,Integer> stat = Lambdas::twice;
        System.out.println("stat=" + stat.apply(a));
    }

    static int twice(int v) { return v * 2; }
}
