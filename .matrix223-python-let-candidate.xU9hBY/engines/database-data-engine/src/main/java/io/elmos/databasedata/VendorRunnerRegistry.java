package io.elmos.databasedata;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.databasedata.DatabaseDataModels.*;

public final class VendorRunnerRegistry {
    private static final Set<String> READ_ONLY = Set.of(
            "METADATA_READ", "CATALOG_READ", "PLAN_READ", "PERFORMANCE_VIEW_READ");
    private static final Set<String> PRODUCTION = Set.of(
            "DDL", "DML", "REPLICATION_ADMIN", "LOGGING_CHANGE", "CDC_START", "WRITER_CUTOVER");

    private final Map<DatabaseVendor, RunnerProfile> profiles;

    public VendorRunnerRegistry() {
        var configured = new EnumMap<DatabaseVendor, RunnerProfile>(DatabaseVendor.class);
        configured.put(DatabaseVendor.ORACLE, profile(DatabaseVendor.ORACLE,
                "SQL*Plus", "SQLcl", "Data Pump", "DBMS_METADATA", "AWR/ASH", "GoldenGate"));
        configured.put(DatabaseVendor.SQL_SERVER, profile(DatabaseVendor.SQL_SERVER,
                "sqlcmd", "bcp", "DacFx", "Query Store", "Execution Plan", "SSMA"));
        configured.put(DatabaseVendor.MYSQL, profile(DatabaseVendor.MYSQL,
                "mysql", "mysqlsh", "MySQL Shell Dump/Load", "Performance Schema", "Binary Log"));
        configured.put(DatabaseVendor.POSTGRESQL, profile(DatabaseVendor.POSTGRESQL,
                "psql", "pg_dump", "pg_restore", "pg_upgrade", "Logical Replication", "pg_stat_statements"));
        configured.put(DatabaseVendor.DATA_PLATFORM, profile(DatabaseVendor.DATA_PLATFORM,
                "Spark", "Flink", "Trino", "dbt", "Airflow", "Iceberg", "Delta", "OpenLineage"));
        configured.put(DatabaseVendor.BI_VALIDATION, profile(DatabaseVendor.BI_VALIDATION,
                "Power BI Adapter", "SSRS Adapter", "Tableau Adapter", "Metric Comparator"));
        this.profiles = Map.copyOf(configured);
    }

    public RunnerProfile require(DatabaseVendor vendor) {
        var profile = profiles.get(vendor);
        if (profile == null) throw new IllegalArgumentException("runner profile not declared: " + vendor);
        return profile;
    }

    public Map<DatabaseVendor, RunnerProfile> all() {
        return profiles;
    }

    private RunnerProfile profile(DatabaseVendor vendor, String... tools) {
        return new RunnerProfile(vendor, List.of(tools), READ_ONLY, PRODUCTION, true, RunnerStatus.NOT_CONFIGURED);
    }
}
