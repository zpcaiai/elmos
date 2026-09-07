public class BillingAccount {
    private long balanceMicros;
    private long reservedMicros;

    //@ public invariant balanceMicros >= 0;
    //@ public invariant reservedMicros >= 0;

    /*@ public normal_behavior
      @ requires amount >= 0;
      @ requires balanceMicros >= amount;
      @ assignable balanceMicros, reservedMicros;
      @ ensures balanceMicros == \old(balanceMicros) - amount;
      @ ensures reservedMicros == \old(reservedMicros) + amount;
      @ also public exceptional_behavior
      @ requires amount < 0 || balanceMicros < amount;
      @ assignable \nothing;
      @ signals_only IllegalArgumentException;
      @*/
    public void reserve(long amount) {
        if (amount < 0 || balanceMicros < amount) {
            throw new IllegalArgumentException("invalid reservation");
        }
        balanceMicros -= amount;
        reservedMicros += amount;
    }
}
