// A functional interface declared in its own file.  The lambda that implements
// it is written in Ledger.java, so the emitter can only know which method the
// call dispatches to by looking the interface up in the index.
public interface Adjust {
    int apply(int value);
}
