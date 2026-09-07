// Half of a cross-file program: nothing here is called from this file.
// Every method below exists to be reached from Ledger.java, which is the whole
// point -- a one-file-at-a-time engine cannot type any of these calls.
public final class Rates {

    static final int BASE = 100;
    static final int LIMIT = Integer.MAX_VALUE;

    private final int factor;

    Rates(int factor) {
        this.factor = factor;
    }

    // Overflow has to wrap at 32 bits on both sides of the migration, and the
    // call site is in another file, so the emitter only knows the return type
    // is `int` because the index told it.
    static int product(int a, int b) {
        return a * b;
    }

    // Truncating division and dividend-signed remainder, reached across files.
    static int share(int amount, int parts) {
        return amount / parts;
    }

    static int leftover(int amount, int parts) {
        return amount % parts;
    }

    // Varargs packed at the *call site*, in the other file.
    static int total(int... values) {
        int sum = 0;
        for (int v : values) {
            sum += v;
        }
        return sum;
    }

    int scale(int amount) {
        return amount * factor;
    }

    // Deliberately *not* named `factor`: Java would allow a method and a
    // field to share the name, and the emitter refuses that (see the
    // field/method namespace clash test) rather than silently overwriting one.
    int currentFactor() {
        return factor;
    }
}
