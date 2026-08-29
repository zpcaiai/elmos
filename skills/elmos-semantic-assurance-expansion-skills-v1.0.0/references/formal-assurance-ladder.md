# Formal Assurance Ladder

Use the weakest adequate and scalable method: static invariants → bounded SMT/BMC → symbolic execution → LLVM refinement/translation validation → verified lowering where available. Formal proof scope must be explicit and is combined with runtime evidence for external systems, concurrency, UI, DB and operational behavior. `unknown` or timeout is never `pass`.
