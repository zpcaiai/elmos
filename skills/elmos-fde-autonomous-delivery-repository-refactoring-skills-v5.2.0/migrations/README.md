# Persistence migrations

These PostgreSQL files are additive reference migrations. They intentionally omit organization-specific RLS policies, partitioning, retention jobs and encryption integration. Bind them to the target Elmos canonical persistence model; do not create a parallel Goal or runtime-authority store. Test on a disposable PostgreSQL 17 instance before use.
