public class Resources {
    static class Res implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;
        Res(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open " + name);
        }
        void use() { System.out.println("use " + name); }
        public void close() {
            System.out.println("close " + name);
            if (failOnClose) { throw new IllegalStateException("close " + name); }
        }
    }

    static int varargs(int base, int... rest) {
        int total = base;
        for (int v : rest) { total += v; }
        return total * 10 + rest.length;
    }

    static <A> A identity(A value) { return value; }

    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);

        // Closed in reverse order, before catch and finally run.
        try (Res one = new Res("one", false); Res two = new Res("two", false)) {
            one.use();
            two.use();
        } finally {
            System.out.println("after");
        }

        // A close() failure while the body is throwing must be suppressed:
        // the body's exception is the one that propagates.
        try (Res bad = new Res("bad", true)) {
            throw new IllegalArgumentException("from body");
        } catch (RuntimeException e) {
            System.out.println("caught=" + e.getMessage());
        }

        // A close() failure with no in-flight exception does propagate.
        try (Res bad2 = new Res("bad2", true)) {
            System.out.println("clean body");
        } catch (RuntimeException e) {
            System.out.println("caught2=" + e.getMessage());
        }

        System.out.println("va0=" + varargs(a));
        System.out.println("va1=" + varargs(a, 1));
        System.out.println("va3=" + varargs(a, 1, 2, 3));
        System.out.println("gen=" + identity("g") + identity(a));
    }
}
