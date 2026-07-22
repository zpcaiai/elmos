package io.elmos.databasedata;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Loss-preserving vendor-neutral schema, SQL, and procedure intermediate representation. */
public final class CanonicalDatabaseIr {
    private CanonicalDatabaseIr() {}

    public enum CanonicalType {
        BOOLEAN, INT16, INT32, INT64, DECIMAL, FLOAT32, FLOAT64, CHAR, VARCHAR,
        TEXT, BINARY, DATE, TIME, TIMESTAMP, TIMESTAMP_TZ, INTERVAL, UUID, JSON,
        XML, ARRAY, ENUM, LOB, SPATIAL, VENDOR_SPECIFIC
    }
    public enum SqlOperation {
        SELECT, INSERT, UPDATE, DELETE, MERGE, UPSERT, DDL, CTE, WINDOW,
        AGGREGATE, PIVOT, HIERARCHICAL, JSON, XML, TEMPORAL, DYNAMIC_SQL
    }
    public enum ProcedureOperation {
        BLOCK, DECLARE, ASSIGN, IF, LOOP, CURSOR, EXCEPTION, TRANSACTION,
        DYNAMIC_SQL, CALL, RETURN, RAISE, TEMP_TABLE, BULK_OPERATION
    }
    public enum DynamicSqlStatus { PARSED_CONSTANT, PARTIALLY_PARSED, RUNTIME_DEPENDENT, UNRESOLVED }
    public enum DependencyType { READS, WRITES, CALLS, TRIGGERS, SCHEDULES, LINKS, REPORTS, DERIVES }

    public record Provenance(
            DatabaseDataModels.DatabaseVendor vendor,
            String sourceObject,
            String sourceRange,
            String sourceHash,
            List<String> evidenceRefs) {
        public Provenance {
            Objects.requireNonNull(vendor);
            require(sourceObject, "sourceObject");
            require(sourceHash, "sourceHash");
            evidenceRefs = List.copyOf(evidenceRefs);
            if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("IR provenance evidence is required");
        }
    }

    public record CanonicalTypeRef(
            CanonicalType canonicalType,
            Integer precision,
            Integer scale,
            Integer length,
            boolean nullable,
            Map<String, Object> vendorExtension) {
        public CanonicalTypeRef {
            Objects.requireNonNull(canonicalType);
            vendorExtension = Map.copyOf(vendorExtension);
            if (canonicalType == CanonicalType.VENDOR_SPECIFIC && vendorExtension.isEmpty()) {
                throw new IllegalArgumentException("vendor-specific type requires extension");
            }
        }
    }

    public record ColumnNode(
            String columnId,
            String name,
            CanonicalTypeRef type,
            String defaultExpression,
            String generatedExpression,
            Provenance provenance) {
        public ColumnNode {
            require(columnId, "columnId"); require(name, "name");
            Objects.requireNonNull(type); Objects.requireNonNull(provenance);
        }
    }

    public record SchemaObjectNode(
            String objectId,
            String catalog,
            String schema,
            String name,
            String objectType,
            List<ColumnNode> columns,
            Map<String, Object> vendorExtension,
            Provenance provenance) {
        public SchemaObjectNode {
            require(objectId, "objectId"); require(schema, "schema");
            require(name, "name"); require(objectType, "objectType");
            columns = List.copyOf(columns);
            vendorExtension = Map.copyOf(vendorExtension);
            Objects.requireNonNull(provenance);
        }
    }

    public record SqlNode(
            String statementId,
            SqlOperation operation,
            List<String> objectRefs,
            DynamicSqlStatus dynamicSqlStatus,
            Map<String, Object> canonicalExpression,
            Map<String, Object> vendorExtension,
            Provenance provenance) {
        public SqlNode {
            require(statementId, "statementId");
            Objects.requireNonNull(operation);
            objectRefs = List.copyOf(objectRefs);
            Objects.requireNonNull(dynamicSqlStatus);
            canonicalExpression = Map.copyOf(canonicalExpression);
            vendorExtension = Map.copyOf(vendorExtension);
            Objects.requireNonNull(provenance);
        }

        public boolean eligibleForAutomaticTargetEmission() {
            return dynamicSqlStatus != DynamicSqlStatus.RUNTIME_DEPENDENT
                    && dynamicSqlStatus != DynamicSqlStatus.UNRESOLVED;
        }
    }

    public record ProcedureStatement(
            String statementId,
            ProcedureOperation operation,
            List<String> objectRefs,
            Map<String, Object> semantics) {
        public ProcedureStatement {
            require(statementId, "statementId");
            Objects.requireNonNull(operation);
            objectRefs = List.copyOf(objectRefs);
            semantics = Map.copyOf(semantics);
        }
    }

    public record ProcedureNode(
            String routineId,
            String routineType,
            List<ProcedureStatement> statements,
            boolean sessionStateful,
            boolean autonomousTransaction,
            Map<String, Object> vendorExtension,
            Provenance provenance) {
        public ProcedureNode {
            require(routineId, "routineId"); require(routineType, "routineType");
            statements = List.copyOf(statements);
            vendorExtension = Map.copyOf(vendorExtension);
            Objects.requireNonNull(provenance);
        }

        public boolean requiresManualRedesign() {
            return sessionStateful || autonomousTransaction
                    || statements.stream().anyMatch(value -> value.operation() == ProcedureOperation.DYNAMIC_SQL);
        }
    }

    public record DependencyEdge(
            String fromId,
            String toId,
            DependencyType type,
            String evidenceRef) {
        public DependencyEdge {
            require(fromId, "fromId"); require(toId, "toId");
            Objects.requireNonNull(type); require(evidenceRef, "evidenceRef");
        }
    }

    public record Snapshot(
            String schemaVersion,
            String organizationId,
            String snapshotRef,
            List<SchemaObjectNode> schemaObjects,
            List<SqlNode> sql,
            List<ProcedureNode> procedures,
            List<DependencyEdge> dependencies) {
        public Snapshot {
            if (!"1.0".equals(schemaVersion)) throw new IllegalArgumentException("unsupported IR schema version");
            require(organizationId, "organizationId"); require(snapshotRef, "snapshotRef");
            schemaObjects = List.copyOf(schemaObjects);
            sql = List.copyOf(sql);
            procedures = List.copyOf(procedures);
            dependencies = List.copyOf(dependencies);
            var ids = new java.util.HashSet<String>();
            schemaObjects.forEach(value -> addUnique(ids, value.objectId()));
            sql.forEach(value -> addUnique(ids, value.statementId()));
            procedures.forEach(value -> addUnique(ids, value.routineId()));
            Set<String> known = Set.copyOf(ids);
            if (dependencies.stream().anyMatch(value -> !known.contains(value.fromId())
                    || !known.contains(value.toId()))) {
                throw new IllegalArgumentException("dependency references unknown IR node");
            }
        }
    }

    private static void addUnique(Set<String> ids, String id) {
        if (!ids.add(id)) throw new IllegalArgumentException("duplicate IR identity: " + id);
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
