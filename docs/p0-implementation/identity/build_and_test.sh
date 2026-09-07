#!/usr/bin/env bash
# Build the identity module and run both suites.
#
# The service suite needs a real PostgreSQL with V1..V55 applied. It is created
# from a template database so every run starts on a clean schema - a suite that
# depends on leftovers from the previous run proves nothing the second time.
set -euo pipefail
cd "$(dirname "$0")"

PGHOST=${PGHOST:-127.0.0.1}
PGPORT=${PGPORT:-5433}
PGUSER=${PGUSER:-elmos}
TEMPLATE=${TEMPLATE:-elmos_auth_template}
DB=${DB:-elmos_auth_run}
DRIVER=${DRIVER:-/usr/share/java/postgresql.jar}

rm -rf target && mkdir -p target/classes target/test-classes

echo "==> compiling identity module"
javac -Xlint:all -d target/classes $(find src/main/java -name '*.java')

echo "==> compiling tests"
javac -d target/test-classes -cp "target/classes:$DRIVER" $(find src/test/java -name '*.java')

echo "==> identity core acceptance"
java -cp target/classes:target/test-classes io.elmos.identity.IdentityCoreTest

if psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname='$TEMPLATE'" 2>/dev/null | grep -q 1; then
  echo "==> resetting $DB from template $TEMPLATE"
  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -q \
       -c "DROP DATABASE IF EXISTS $DB" -c "CREATE DATABASE $DB TEMPLATE $TEMPLATE"
  echo "==> authentication service acceptance (real PostgreSQL)"
  ELMOS_TEST_JDBC_URL="jdbc:postgresql://$PGHOST:$PGPORT/$DB?user=$PGUSER" \
    java -cp "target/classes:target/test-classes:$DRIVER" \
      io.elmos.identity.AuthenticationServiceTest
else
  echo "==> skipping the service suite: template database $TEMPLATE not found"
  echo "    create it by applying V1..V55 to a database of that name"
fi
