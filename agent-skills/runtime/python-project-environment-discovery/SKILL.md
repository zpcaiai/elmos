---
name: python-project-environment-discovery
description: Discover Python project roots, interpreters, package managers, dependency declarations, entry points, frameworks, notebooks, system packages, containers, CI, and redacted indexes. Use for Python repository intake, monorepo analysis, version-conflict diagnosis, or environment inventory generation.
---

# Python Project and Environment Discovery

## Discover without execution

Scan `pyproject.toml`, setup files, requirements/constraints, Pipenv, Poetry, uv, pylock, Conda, tox/nox, type/lint configs, containers, CI, runtime files, and notebooks. Never execute `setup.py`, import customer modules, follow symlinks, or read outside the approved workspace.

Identify single packages, multi-package monorepos, uv/Poetry/Conda projects, Django/Flask apps, pipelines, ML projects, notebooks, and script collections. Preserve every plausible root; report ambiguity instead of choosing silently.

## Keep version evidence distinct

Record separately:

- `DECLARED_PYTHON`
- `LOCK_RESOLUTION_PYTHON`
- `BUILD_PYTHON`
- `TEST_PYTHON`
- `DEPLOYMENT_PYTHON`

Prioritize observed baseline and deployment evidence over metadata, but never overwrite conflicting values.

## Inventory behavior and dependencies

Find console/module entries, Django WSGI/ASGI/manage, Flask apps, Celery/Airflow/Spark tasks, Lambda/model serving, cron scripts, and notebooks. Capture package-manager conflicts, private indexes, direct URLs, Git/path/editable dependencies, wheelhouses, and system libraries. Redact URL userinfo and all credential values.

## Emit findings

Use explicit findings including `PYTHON_VERSION_CONFLICT`, `MULTIPLE_DEPENDENCY_MANAGERS`, `UNPINNED_DEPENDENCIES`, `PRIVATE_INDEX_REQUIRED`, `SYSTEM_PACKAGE_REQUIRED`, `NOTEBOOK_ONLY_LOGIC`, and `ENTRY_POINT_UNRESOLVED`.

Accept only when monorepo roots remain visible, versions retain their source roles, notebooks/scripts are included, system dependencies enter the model, and no credential appears in output.

