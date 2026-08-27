------------------------------ MODULE TaskRuntime ------------------------------
EXTENDS Naturals, FiniteSets, Sequences

CONSTANTS Accounts, Tasks, Workers, MaxConcurrent, NoOwner
ASSUME MaxConcurrent = 3

VARIABLES state, account, owner, token, committed, cancelled

States == {"Queued", "Leased", "Running", "Paused", "Succeeded", "Failed", "Cancelled"}

Init ==
  /\ state = [t \in Tasks |-> "Queued"]
  /\ owner = [t \in Tasks |-> NoOwner]
  /\ token = [t \in Tasks |-> 0]
  /\ committed = {}
  /\ cancelled = {}

Active(a) == {t \in Tasks : account[t] = a /\ state[t] \in {"Leased", "Running", "Paused"}}

Lease(t, w) ==
  /\ state[t] \in {"Queued", "Paused"}
  /\ Cardinality(Active(account[t])) < MaxConcurrent
  /\ state' = [state EXCEPT ![t] = "Leased"]
  /\ owner' = [owner EXCEPT ![t] = w]
  /\ token' = [token EXCEPT ![t] = @ + 1]
  /\ UNCHANGED <<committed, cancelled>>

Start(t, w, f) ==
  /\ state[t] = "Leased"
  /\ owner[t] = w
  /\ token[t] = f
  /\ state' = [state EXCEPT ![t] = "Running"]
  /\ UNCHANGED <<owner, token, committed, cancelled>>

Commit(t, w, f) ==
  /\ state[t] = "Running"
  /\ owner[t] = w
  /\ token[t] = f
  /\ t \notin cancelled
  /\ state' = [state EXCEPT ![t] = "Succeeded"]
  /\ committed' = committed \cup {t}
  /\ UNCHANGED <<owner, token, cancelled>>

Cancel(t) ==
  /\ state[t] \in {"Queued", "Leased", "Running", "Paused"}
  /\ state' = [state EXCEPT ![t] = "Cancelled"]
  /\ cancelled' = cancelled \cup {t}
  /\ UNCHANGED <<owner, token, committed>>

Next ==
  \/ \E t \in Tasks, w \in Workers : Lease(t, w)
  \/ \E t \in Tasks, w \in Workers, f \in Nat : Start(t, w, f)
  \/ \E t \in Tasks, w \in Workers, f \in Nat : Commit(t, w, f)
  \/ \E t \in Tasks : Cancel(t)

TypeOK ==
  /\ state \in [Tasks -> States]
  /\ token \in [Tasks -> Nat]
  /\ committed \subseteq Tasks
  /\ cancelled \subseteq Tasks

AccountConcurrency == \A a \in Accounts : Cardinality(Active(a)) <= MaxConcurrent
CancelledNotCommitted == cancelled \cap committed = {}
TerminalStable == \A t \in Tasks : state[t] \in {"Succeeded","Failed","Cancelled"} => t \notin Active(account[t])

Spec == Init /\ [][Next]_<<state, owner, token, committed, cancelled>>
Safety == TypeOK /\ AccountConcurrency /\ CancelledNotCommitted /\ TerminalStable
=============================================================================
