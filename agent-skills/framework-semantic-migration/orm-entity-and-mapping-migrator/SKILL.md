---
name: orm-entity-and-mapping-migrator
description: "Migrate ORM entities, schema mappings, keys, relations, loading, tracking, concurrency, indexes, and tenant metadata. Use for JPA, SQLAlchemy, EF Core, TypeORM, Prisma, Sequelize, Mongoose, or raw mapping conversion."
---
# ORM Entity and Mapping Migrator
Read `../references/afsm-v1.md`. Preserve table/schema/column, key generation, nullability, Decimal precision/scale, converters, relations, cascade/orphan behavior, fetch/loading, ownership, inheritance, filters, indexes, concurrency and tenant fields.

Keep DTOs separate from entities and make naming/tracking/unit-of-work defaults explicit. Prefer schema plus domain-contract preservation during initial migration. Block guessed keys, lost precision or unplanned lazy/eager changes.

