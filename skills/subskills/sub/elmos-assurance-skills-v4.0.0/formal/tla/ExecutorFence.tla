------------------------- MODULE ExecutorFence -------------------------
EXTENDS Naturals, FiniteSets
CONSTANT MaxEpoch
VARIABLES epoch, live, attempts, commits
vars == <<epoch, live, attempts, commits>>
Init == /\ epoch = 1 /\ live = TRUE /\ attempts = {} /\ commits = {}
Dispatch == /\ live /\ attempts' = attempts \cup {epoch}
            /\ UNCHANGED <<epoch, live, commits>>
Replace == /\ live /\ epoch < MaxEpoch /\ epoch' = epoch + 1
           /\ UNCHANGED <<live, attempts, commits>>
Cancel == /\ live /\ live' = FALSE /\ UNCHANGED <<epoch, attempts, commits>>
Commit(e) == /\ live /\ e \in attempts /\ e = epoch /\ commits = {}
             /\ commits' = {<<e, epoch, live>>}
             /\ UNCHANGED <<epoch, live, attempts>>
Next == Dispatch \/ Replace \/ Cancel \/ (\E e \in 1..MaxEpoch : Commit(e))
Spec == Init /\ [][Next]_vars
TypeOK == /\ epoch \in 1..MaxEpoch /\ live \in BOOLEAN
          /\ attempts \subseteq 1..MaxEpoch
          /\ commits \subseteq ((1..MaxEpoch) \X (1..MaxEpoch) \X BOOLEAN)
AtMostOneCommit == Cardinality(commits) <= 1
NoStaleAtCommit == \A c \in commits : c[1] = c[2] /\ c[3] = TRUE
=============================================================================
