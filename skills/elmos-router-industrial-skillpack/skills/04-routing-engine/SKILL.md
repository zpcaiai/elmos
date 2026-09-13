# Skill 04 — Routing Engine

## Goal
Deterministically choose the best eligible deployment for each Elmos step.

## Algorithm

### Phase A — hard eligibility
Filter with Skill 03 policies.

### Phase B — normalized scoring
For each eligible candidate compute a score from:
- capability fit
- task-specific benchmark quality
- reliability/health
- expected latency
- estimated cost
- cache affinity
- region affinity
- provider diversity
- historical task-class success

Recommended structure:

`score = Σ(weight_i * normalized_feature_i) - penalties`

Never encode policy denial as a low score.

### Phase C — tie-break
Stable deterministic tie-break:
1. higher policy priority
2. lower projected cost
3. higher health
4. stable deployment id lexical order

### Phase D — fallback graph
Generate ordered fallbacks with constraints:
- same required capabilities;
- no compliance weakening;
- no budget bypass;
- provider diversity preferred;
- avoid repeatedly selecting same outage domain;
- preserve native lane if required.

## Task classes
Start with Elmos-specific classes:
- REPO_ANALYSIS
- ARCHITECTURE_REASONING
- CODE_GENERATION
- LARGE_REFACTOR
- MIGRATION_PLANNING
- MIGRATION_EXECUTION
- TEST_GENERATION
- DEBUGGING
- SQL_TRANSLATION
- FORMAL_VERIFICATION
- DOCUMENTATION
- CHEAP_CLASSIFICATION
- EMBEDDING
- RERANKING

## Shadow mode
For every production request, optionally compute route-v2 decision without executing it. Compare:
- selected model/provider,
- estimated cost,
- expected quality tier,
- policy differences,
- latency projection.

## Acceptance
- Given same config/health snapshot/request, decision is deterministic.
- Route decision contains score explanation.
- Policy-ineligible candidate can never win.
- Property tests cover candidate permutations.
