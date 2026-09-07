// A record in its own file: the component accessors, the generated toString and
// the static factory all have to be resolvable from Ledger.java.
public record Money(String label, long cents) {

    public Money {
        if (cents < 0) {
            throw new IllegalArgumentException("negative: " + cents);
        }
    }

    public static Money of(String label, long cents) {
        return new Money(label, cents);
    }

    public String render() {
        return label + "=" + cents;
    }

    public long doubled() {
        return cents * 2;
    }
}
