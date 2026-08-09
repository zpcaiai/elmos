
# Batch 31 Version and Recertification Policy

- Use exact source/target versions and editions. `latest`, `*`, `x`, mutable image tags, and unspecified cloud service tiers are prohibited.
- Lock driver/client, migration tool, container, extension, compatibility mode, and time-zone data versions.
- A patch update can require recertification when it changes optimizer, collation, parser, replication, driver, security, or routine behavior.
- Major/minor engine upgrades are separate route tuples, even when source and target products are the same.
- Record support start, review date, maintenance owner, deprecation, and EOL.
- Existing long-running migrations remain bound to their original pack, IR, transformation, runner, and target-profile snapshots.
- Recertify after material changes to engine, edition, driver, extension, SQL mode, target provider, canonical IR, transformation, data migration, or gate corpus.
