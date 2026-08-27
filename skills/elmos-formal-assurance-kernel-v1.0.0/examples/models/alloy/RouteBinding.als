module RouteBinding
sig LegacyRoute { pattern: one Pattern, priority: one Int }
sig TargetRoute { pattern: one Pattern, priority: one Int }
sig Pattern {}
one sig Mapped {
  relation: LegacyRoute -> one TargetRoute
}

fact CompleteMapping {
  all l: LegacyRoute | one Mapped.relation[l]
}

fact UniqueTargetWinner {
  all p: Pattern | lone { t: TargetRoute | t.pattern = p and
    no t2: TargetRoute | t2.pattern = p and t2.priority > t.priority }
}

assert NoLegacyRouteLost {
  all l: LegacyRoute | some Mapped.relation[l]
}
check NoLegacyRouteLost for 8
