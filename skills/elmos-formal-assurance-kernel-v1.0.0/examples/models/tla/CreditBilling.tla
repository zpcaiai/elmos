------------------------------ MODULE CreditBilling ------------------------------
EXTENDS Naturals, FiniteSets

CONSTANTS Accounts, Events, InitialBalance
VARIABLES balance, reserved, consumed, refundable, charged

Init ==
  /\ balance = [a \in Accounts |-> InitialBalance[a]]
  /\ reserved = [a \in Accounts |-> 0]
  /\ consumed = [a \in Accounts |-> 0]
  /\ refundable = [a \in Accounts |-> 0]
  /\ charged = {}

Reserve(a, amount) ==
  /\ amount \in Nat
  /\ amount <= balance[a]
  /\ balance' = [balance EXCEPT ![a] = @ - amount]
  /\ reserved' = [reserved EXCEPT ![a] = @ + amount]
  /\ UNCHANGED <<consumed, refundable, charged>>

Consume(a, e, amount) ==
  /\ e \notin charged
  /\ amount <= reserved[a]
  /\ reserved' = [reserved EXCEPT ![a] = @ - amount]
  /\ consumed' = [consumed EXCEPT ![a] = @ + amount]
  /\ charged' = charged \cup {e}
  /\ UNCHANGED <<balance, refundable>>

Refund(a, amount) ==
  /\ amount <= reserved[a]
  /\ reserved' = [reserved EXCEPT ![a] = @ - amount]
  /\ refundable' = [refundable EXCEPT ![a] = @ + amount]
  /\ balance' = [balance EXCEPT ![a] = @ + amount]
  /\ UNCHANGED <<consumed, charged>>

Next ==
  \/ \E a \in Accounts, amount \in 0..InitialBalance[a] : Reserve(a, amount)
  \/ \E a \in Accounts, e \in Events, amount \in 0..InitialBalance[a] : Consume(a, e, amount)
  \/ \E a \in Accounts, amount \in 0..InitialBalance[a] : Refund(a, amount)

NonNegative == \A a \in Accounts : balance[a] >= 0
Conservation == \A a \in Accounts :
  balance[a] + reserved[a] + consumed[a] = InitialBalance[a]
NoDuplicateCharge == Cardinality(charged) <= Cardinality(Events)

Spec == Init /\ [][Next]_<<balance, reserved, consumed, refundable, charged>>
=============================================================================
