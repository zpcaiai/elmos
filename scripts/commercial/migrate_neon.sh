#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf '%s\n' "commercial billing migration blocked: $1" >&2
  exit 1
}

required() {
  local name="$1"
  test -n "${!name:-}" || fail "$name is required"
}

required ELMOS_COMMERCIAL_DATABASE_URL
required ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME
required ELMOS_COMMERCIAL_DATABASE_MIGRATION_PASSWORD
required ELMOS_COMMERCIAL_DATABASE_EXPECTED_HOST
required ELMOS_COMMERCIAL_DATABASE_EXPECTED_DATABASE

test "${ELMOS_COMMERCIAL_DATABASE_MIGRATION_CONFIRMED:-}" = "true" \
  || fail "ELMOS_COMMERCIAL_DATABASE_MIGRATION_CONFIRMED must be true"

jdbc_url="$ELMOS_COMMERCIAL_DATABASE_URL"
case "$jdbc_url" in
  jdbc:postgresql://*) ;;
  *) fail "database URL must use jdbc:postgresql" ;;
esac

connection="${jdbc_url#jdbc:postgresql://}"
authority="${connection%%/*}"
database_and_query="${connection#*/}"
database="${database_and_query%%\?*}"
host="${authority%%:*}"

test "$authority" != "$connection" || fail "database URL must include a database"
test "$host" = "$ELMOS_COMMERCIAL_DATABASE_EXPECTED_HOST" \
  || fail "database host does not match the approved target"
test "$database" = "$ELMOS_COMMERCIAL_DATABASE_EXPECTED_DATABASE" \
  || fail "database name does not match the approved target"
case "$host" in
  *.neon.tech) ;;
  *) fail "approved production migration target must be a Neon endpoint" ;;
esac
case "$jdbc_url" in
  *"sslmode=require"*|*"sslmode=verify-full"*) ;;
  *) fail "database URL must require TLS" ;;
esac
case "$jdbc_url" in
  *"password="*|*"@"*) fail "credentials must not be embedded in the database URL" ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd "$script_dir/../.." && pwd)"
module_pom="$repository_root/modules/persistence/pom.xml"

printf '%s\n' "Target verified: Neon host and database match the approved environment."
printf '%s\n' "Compiling the exact migration module before applying migrations."
mvn -B -ntp -q -DskipTests -pl modules/persistence -am install -f "$repository_root/pom.xml"

flyway_common=(
  -B
  -ntp
  -f "$module_pom"
  "-Dflyway.url=$jdbc_url"
  "-Dflyway.user=$ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME"
  "-Dflyway.password=$ELMOS_COMMERCIAL_DATABASE_MIGRATION_PASSWORD"
)

printf '%s\n' "Validating applied migration checksums."
mvn "${flyway_common[@]}" "-Dflyway.ignoreMigrationPatterns=*:pending" flyway:validate
printf '%s\n' "Applying pending migrations under Flyway schema-history control."
mvn "${flyway_common[@]}" flyway:migrate
printf '%s\n' "Re-validating the complete migration chain."
mvn "${flyway_common[@]}" flyway:validate
printf '%s\n' "Applying least-privileged billing runtime grants."
bash "$script_dir/configure_billing_runtime_role.sh"
printf '%s\n' "Commercial billing migration completed and validated."
