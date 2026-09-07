#!/usr/bin/env bash
# Bring up (or re-attach to) the two servers the execution evidence needs, and
# FAIL LOUDLY if either is not actually answering.
#
# The container reclaims background processes, so a harness that assumes the
# servers from ten minutes ago are still up will silently produce numbers from
# a partial run. Every evidence run must start here.
set -uo pipefail
export PGDATA=${PGDATA:-/tmp/pgdata} PGPORT=${PGPORT:-55432}
MYSOCK=${MYSOCK:-/tmp/mysqld/m.sock}

if ! pg_isready -h /tmp -p "$PGPORT" >/dev/null 2>&1; then
  [ -d "$PGDATA/base" ] || { rm -rf "$PGDATA"; mkdir -p "$PGDATA"; chown postgres:postgres "$PGDATA" /tmp
    su postgres -c "/usr/lib/postgresql/16/bin/initdb -D $PGDATA -A trust -U postgres" >/tmp/initdb.log 2>&1; }
  chown -R postgres:postgres "$PGDATA" 2>/dev/null
  su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D $PGDATA -o '-p $PGPORT -k /tmp' -l /tmp/pg.log start" >/dev/null 2>&1
  for _ in $(seq 1 30); do pg_isready -h /tmp -p "$PGPORT" >/dev/null 2>&1 && break; sleep 1; done
fi

if ! mysqladmin --socket="$MYSOCK" -u root ping >/dev/null 2>&1; then
  mkdir -p /tmp/mysqld && chown -R mysql:mysql /tmp/mysqld 2>/dev/null
  [ -d /tmp/mysqldata/mysql ] || { rm -rf /tmp/mysqldata; mkdir -p /tmp/mysqldata; chown mysql:mysql /tmp/mysqldata
    mysqld --initialize-insecure --user=mysql --datadir=/tmp/mysqldata >/tmp/mysqlinit.log 2>&1; }
  nohup mysqld --user=mysql --datadir=/tmp/mysqldata --socket="$MYSOCK" --port=33306 \
        --pid-file=/tmp/mysqld/m.pid >/tmp/mysqld.log 2>&1 &
  for _ in $(seq 1 40); do mysqladmin --socket="$MYSOCK" -u root ping >/dev/null 2>&1 && break; sleep 1; done
fi

pg_isready -h /tmp -p "$PGPORT" >/dev/null 2>&1 || { echo "FATAL: PostgreSQL is not answering"; exit 1; }
mysqladmin --socket="$MYSOCK" -u root ping >/dev/null 2>&1 || { echo "FATAL: MySQL is not answering"; exit 1; }

psql -h /tmp -p "$PGPORT" -U postgres -tAc "select version();" | cut -c1-40
mysql --socket="$MYSOCK" -u root -N -B -e "select concat(version(),' / ',@@collation_server);"
# The regex evidence depends on this being the case-INsensitive default.
mysql --socket="$MYSOCK" -u root -N -B -e "select @@collation_server;" | grep -q '_ci$' \
  || echo "WARNING: server collation is case-sensitive; the regex counterfactual will pass for the wrong reason"
