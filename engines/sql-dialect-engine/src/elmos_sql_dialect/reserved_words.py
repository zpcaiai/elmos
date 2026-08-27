"""Target-dialect reserved words, each list carrying HOW IT WAS ESTABLISHED.

An unquoted identifier equal to a reserved word is a syntax error on the
target while the source accepts it happily. The corpus hit this with a column
literally named `signal`, and `sqlglot` re-parsed the emission without
complaint -- its dialects do not model reserved words -- so only a real server
caught it.

The lists therefore carry provenance, because "MySQL rejects these, measured"
and "the vendor documents these" are not the same claim and must not be
reported as if they were:

    EXECUTION_VERIFIED  every word was fed to a real server as an identifier
                        and observed to be refused. `evidence/
                        verify_reserved_words.py` produces this.
    VENDOR_DOCUMENTED   taken from the vendor's own keyword list. Refusing on
                        it can only ever cost a false BLOCK, never allow a bad
                        emission -- the conservative direction -- but it has
                        NOT been proven against a running server.

Oracle and SQL Server sit at VENDOR_DOCUMENTED because neither has a free
rootless local instance, and in this environment `download.oracle.com`,
`packages.microsoft.com` and every container registry are refused by the egress
proxy (measured, HTTP 000/403). Running the verifier against any real instance
upgrades them; nothing else should.
"""

from __future__ import annotations

from enum import Enum

from .models import Dialect


class Provenance(str, Enum):
    EXECUTION_VERIFIED = "EXECUTION_VERIFIED"
    VENDOR_DOCUMENTED = "VENDOR_DOCUMENTED"


#: MySQL 8.0. Every entry refused as an identifier by a real MySQL 8.0.46 --
#: see `.ai/measurement-2026-08-25/reserved-words-evidence.json`.
MYSQL: frozenset[str] = frozenset({
    "accessible", "add", "all", "alter", "analyze", "and", "as", "asc", "asensitive", "before",
    "between", "bigint", "binary", "blob", "both", "by", "call", "cascade", "case", "change",
    "char", "character", "check", "collate", "column", "condition", "constraint", "continue",
    "convert", "create", "cross", "cube", "cume_dist", "current_date", "current_time", "current_timestamp",
    "current_user", "cursor", "database", "databases", "day_hour", "day_microsecond", "day_minute",
    "day_second", "dec", "decimal", "declare", "default", "delayed", "delete", "dense_rank",
    "desc", "describe", "deterministic", "distinct", "distinctrow", "div", "double", "drop",
    "dual", "each", "else", "elseif", "empty", "enclosed", "escaped", "except", "exists",
    "exit", "explain", "false", "fetch", "first_value", "float", "float4", "float8", "for",
    "force", "foreign", "from", "fulltext", "function", "generated", "get", "grant", "group",
    "grouping", "groups", "having", "high_priority", "hour_microsecond", "hour_minute", "hour_second",
    "if", "ignore", "in", "index", "infile", "inner", "inout", "insensitive", "insert", "int",
    "int1", "int2", "int3", "int4", "int8", "integer", "interval", "into", "io_after_gtids",
    "io_before_gtids", "is", "iterate", "join", "json_table", "key", "keys", "kill", "lag",
    "last_value", "lateral", "lead", "leading", "leave", "left", "like", "limit", "linear",
    "lines", "load", "localtime", "localtimestamp", "lock", "long", "longblob", "longtext",
    "loop", "low_priority", "master_bind", "master_ssl_verify_server_cert", "match", "maxvalue",
    "mediumblob", "mediumint", "mediumtext", "middleint", "minute_microsecond", "minute_second",
    "mod", "modifies", "natural", "no_write_to_binlog", "not", "nth_value", "ntile", "null",
    "numeric", "of", "on", "optimize", "optimizer_costs", "option", "optionally", "or", "order",
    "out", "outer", "outfile", "over", "partition", "percent_rank", "precision", "primary",
    "procedure", "purge", "range", "rank", "read", "read_write", "reads", "real", "recursive",
    "references", "regexp", "release", "rename", "repeat", "replace", "require", "resignal",
    "restrict", "return", "revoke", "right", "rlike", "row", "row_number", "rows", "schema",
    "schemas", "second_microsecond", "select", "sensitive", "separator", "set", "show", "signal",
    "smallint", "spatial", "specific", "sql", "sql_big_result", "sql_calc_found_rows", "sql_small_result",
    "sqlexception", "sqlstate", "sqlwarning", "ssl", "starting", "stored", "straight_join",
    "system", "table", "terminated", "then", "tinyblob", "tinyint", "tinytext", "to", "trailing",
    "trigger", "true", "undo", "union", "unique", "unlock", "unsigned", "update", "usage",
    "use", "using", "utc_date", "utc_time", "utc_timestamp", "values", "varbinary", "varchar",
    "varcharacter", "varying", "virtual", "when", "where", "while", "window", "with", "write",
    "xor", "year_month", "zerofill",
})


#: Oracle. From the vendor keyword list; `V$RESERVED_WORDS` on a live instance
#: is the authority the verifier reads.
ORACLE: frozenset[str] = frozenset({
        "access", "add", "all", "alter", "and", "any", "as", "asc", "audit", "between", "by",
        "char", "check", "cluster", "column", "column_value", "comment", "compress", "connect",
        "create", "current", "date", "decimal", "default", "delete", "desc", "distinct", "drop",
        "else", "exclusive", "exists", "file", "float", "for", "from", "grant", "group", "having",
        "identified", "immediate", "in", "increment", "index", "initial", "insert", "integer",
        "intersect", "into", "is", "level", "like", "lock", "long", "maxextents", "minus", "mlslabel",
        "mode", "modify", "nested_table_id", "noaudit", "nocompress", "not", "nowait", "null",
        "number", "of", "offline", "on", "online", "option", "or", "order", "pctfree", "prior",
        "public", "raw", "rename", "resource", "revoke", "row", "rowid", "rownum", "rows", "select",
        "session", "set", "share", "size", "smallint", "start", "successful", "synonym", "sysdate",
        "table", "then", "to", "trigger", "uid", "union", "unique", "update", "user", "validate",
        "values", "varchar", "varchar2", "view", "whenever", "where", "with",
})


#: SQL Server (Transact-SQL). From the vendor keyword list.
TSQL: frozenset[str] = frozenset({
        "add", "all", "alter", "and", "any", "as", "asc", "authorization", "backup", "begin",
        "between", "break", "browse", "bulk", "by", "cascade", "case", "check", "checkpoint",
        "close", "clustered", "coalesce", "collate", "column", "commit", "compute", "constraint",
        "contains", "containstable", "continue", "convert", "create", "cross", "current", "current_date",
        "current_time", "current_timestamp", "current_user", "cursor", "database", "dbcc", "deallocate",
        "declare", "default", "delete", "deny", "desc", "disk", "distinct", "distributed", "double",
        "drop", "dump", "else", "end", "errlvl", "escape", "except", "exec", "execute", "exists",
        "exit", "external", "fetch", "file", "fillfactor", "for", "foreign", "freetext", "freetexttable",
        "from", "full", "function", "goto", "grant", "group", "having", "holdlock", "identity",
        "identity_insert", "identitycol", "if", "in", "index", "inner", "insert", "intersect",
        "into", "is", "join", "key", "kill", "left", "like", "lineno", "load", "merge", "national",
        "nocheck", "nonclustered", "not", "null", "nullif", "of", "off", "offsets", "on", "open",
        "opendatasource", "openquery", "openrowset", "openxml", "option", "or", "order", "outer",
        "over", "percent", "pivot", "plan", "precision", "primary", "print", "proc", "procedure",
        "public", "raiserror", "read", "readtext", "reconfigure", "references", "replication",
        "restore", "restrict", "return", "revert", "revoke", "right", "rollback", "rowcount",
        "rowguidcol", "rule", "save", "schema", "securityaudit", "select", "semantickeyphrasetable",
        "semanticsimilaritydetailstable", "semanticsimilaritytable", "session_user", "set", "setuser",
        "shutdown", "some", "statistics", "system_user", "table", "tablesample", "textsize",
        "then", "to", "top", "tran", "transaction", "trigger", "truncate", "try_convert", "tsequal",
        "union", "unique", "unpivot", "update", "updatetext", "use", "user", "values", "varying",
        "view", "waitfor", "when", "where", "while", "with", "within", "writetext",
})


RESERVED_WORDS: dict[Dialect, frozenset[str]] = {
    Dialect.MYSQL: MYSQL,
    Dialect.ORACLE: ORACLE,
    Dialect.TSQL: TSQL,
    # PostgreSQL is deliberately absent: it is the only one of the four whose
    # reserved words this engine has never had to refuse, because the certified
    # identifier shape ([A-Za-z_][A-Za-z0-9_]*, unquoted) is already narrower
    # than what PostgreSQL rejects. Adding a list here without a corpus hit or
    # execution evidence would be guessing.
}

PROVENANCE: dict[Dialect, Provenance] = {
    Dialect.MYSQL: Provenance.EXECUTION_VERIFIED,
    Dialect.ORACLE: Provenance.VENDOR_DOCUMENTED,
    Dialect.TSQL: Provenance.VENDOR_DOCUMENTED,
}
