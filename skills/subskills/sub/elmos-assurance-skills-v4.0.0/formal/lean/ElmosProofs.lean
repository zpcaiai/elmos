-- Candidate reference statements. Native Lean execution: NOT_RUN in this delivery.
-- These statements concern Boolean/finite-list models, not SQL NULL or actual repositories.
namespace ElmosProofs

def survives (guard : Bool) (value : Bool) : Bool := guard && value

theorem guard_false (value : Bool) : survives false value = false := by
  cases value <;> rfl

theorem guard_commutes (a b : Bool) : (a && b) = (b && a) := by
  cases a <;> cases b <;> rfl

def select {α : Type} (p : α → Bool) : List α → List α
  | [] => []
  | x :: xs => if p x then x :: select p xs else select p xs

theorem select_true {α : Type} (xs : List α) : select (fun _ => true) xs = xs := by
  induction xs with
  | nil => rfl
  | cons x xs ih => simp [select, ih]

-- Demonstrates an explicit precondition. It does not discharge real-world applicability.
theorem equality_requires_binding {α : Type} (source target : α)
    (binding : source = target) : source = target := binding

end ElmosProofs
#print axioms ElmosProofs.guard_false
#print axioms ElmosProofs.guard_commutes
#print axioms ElmosProofs.select_true
#print axioms ElmosProofs.equality_requires_binding
