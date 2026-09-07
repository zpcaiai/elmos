// Entry point.  Every interesting line here crosses a file boundary: without a
// whole-program index none of these calls has a type, and the emitter refuses
// the file outright.
public final class Ledger {

    public static void main(String[] args) {
        int a = Integer.parseInt(args[0]);
        int b = Integer.parseInt(args[1]);

        // Static call into another file, on values chosen to overflow.
        System.out.println("product=" + Rates.product(a, b));
        System.out.println("product_max=" + Rates.product(Rates.LIMIT, a));

        // Static field and a constant from another file.
        System.out.println("base=" + Rates.BASE);
        System.out.println("limit=" + Rates.LIMIT);

        // Division and remainder, evaluated over there, with Java's rules.
        if (b != 0) {
            System.out.println("share=" + Rates.share(a, b));
            System.out.println("leftover=" + Rates.leftover(a, b));
            System.out.println("share_neg=" + Rates.share(-a, b));
            System.out.println("leftover_neg=" + Rates.leftover(-a, b));
        }

        // Varargs packed at this call site against the other file's signature.
        System.out.println("total=" + Rates.total(a, b, Rates.BASE));
        System.out.println("total0=" + Rates.total());

        // Constructing another file's class and calling an instance method.
        Rates rates = new Rates(b);
        System.out.println("scale=" + rates.scale(a));
        System.out.println("factor=" + rates.currentFactor());

        // A record from another file: factory, accessor, declared method and
        // the compact constructor's validation.
        Money money = Money.of("acct", (long) a);
        System.out.println("label=" + money.label());
        System.out.println("cents=" + money.cents());
        System.out.println("render=" + money.render());
        System.out.println("doubled=" + money.doubled());
        System.out.println("money=" + money.toString());
        System.out.println("same=" + money.equals(Money.of("acct", (long) a)));

        // An enum from another file: printed, and compared by identity.
        Op op = a > b ? Op.ADD : Op.SUB;
        System.out.println("op=" + op);
        System.out.println("is_add=" + (op == Op.ADD));
        System.out.println("name=" + op.name());
        System.out.println("ordinal=" + op.ordinal());
        System.out.println("keep=" + Op.KEEP);

        // A lambda implementing an interface declared in another file, with a
        // capture, called through that interface's single abstract method.
        int captured = b;
        Adjust adjust = v -> v * captured + Rates.BASE;
        System.out.println("adjust=" + adjust.apply(a));

        // The compact constructor's throw has to cross the boundary too.
        try {
            Money.of("bad", -1L);
            System.out.println("no throw");
        } catch (IllegalArgumentException e) {
            System.out.println("caught=" + e.getMessage());
        }
    }
}
