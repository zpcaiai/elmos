---
name: postgres-role-separation-rls-and-tenant-unit-of-work
description: "Separate PostgreSQL owner, Flyway, runtime, and reporting roles; enforce RLS on every tenant table; and implement an explicit tenant-aware unit of work."
---

# Objective

Make database isolation an independent security boundary.

Required role model:

```text
elmos_admin
  emergency/bootstrap only

elmos_migrator
  runs Flyway and owns created schema objects, or assumes an owner role

elmos_runtime
  application runtime
  NOSUPERUSER
  NOBYPASSRLS
  not the owner of tenant tables

elmos_reporting
  restricted read-only access
