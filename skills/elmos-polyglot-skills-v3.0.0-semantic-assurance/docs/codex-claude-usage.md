# Codex and Claude Code Usage

## Installation into an ELMOS repository

```bash
./install.sh /path/to/elmos
cd /path/to/elmos
python3 elmos-polyglot/scripts/elmos_skills.py validate
```

## Invocation pattern

Tell the coding agent to load one entry Skill and follow hard dependencies:

```text
Use $elmos-spring-legacy-modernizer.
Operate only on the authorized repository snapshot.
Create the baseline and migration plan before editing.
Do not mark unexecuted gates as passed.
Return the Completion Report defined by the Skill.
```

For greenfield work:

```text
Use $elmos-full-project-generator with examples/project-generation-spec.yaml.
Generate an executable requirements graph and target profile first.
No production-scope placeholders or disabled tests.
```

For a route:

```bash
python3 elmos-polyglot/scripts/elmos_skills.py route   --source java --target csharp

python3 elmos-polyglot/scripts/elmos_skills.py scaffold-job   --source java --target csharp --mode convert --output migration-job.yaml
```

The agent should not load all 64 Skill bodies into every prompt. The orchestrator or DAG selects only the current Skill, dependencies, relevant adapters, route profile, policy, and bounded source context.
