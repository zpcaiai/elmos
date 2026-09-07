inductive Expr where
  | lit : Int → Expr
  | add : Expr → Expr → Expr

def eval : Expr → Int
  | .lit n => n
  | .add a b => eval a + eval b

def normalize : Expr → Expr
  | .lit n => .lit n
  | .add (.lit a) (.lit b) => .lit (a + b)
  | .add a b => .add (normalize a) (normalize b)

theorem normalize_preserves (e : Expr) : eval (normalize e) = eval e := by
  induction e with
  | lit n => rfl
  | add a b iha ihb =>
      cases a <;> cases b <;> simp [normalize, eval, iha, ihb]
