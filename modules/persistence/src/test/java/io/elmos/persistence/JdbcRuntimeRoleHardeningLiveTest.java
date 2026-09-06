package io.elmos.persistence;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.nio.charset.StandardCharsets;
import java.util.Objects;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** Exact V89 guard on disposable roles; never alters a deployed runtime role. */
class JdbcRuntimeRoleHardeningLiveTest {
    @Test void unsafeRoleAttributesAndMembershipFailWithoutRepairOrRoleLeak() throws Exception {
        String url=System.getenv("ELMOS_EXECUTION_QUEUE_TEST_JDBC_URL");
        assumeTrue(url!=null&&!url.isBlank(),"requires disposable PostgreSQL");
        if(!"true".equals(System.getenv("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE")))
            throw new IllegalStateException("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE=true required");
        var data=new DriverManagerDataSource(url,
                System.getenv().getOrDefault("ELMOS_EXECUTION_QUEUE_TEST_DATABASE_USER",System.getProperty("user.name")),
                System.getenv().getOrDefault("ELMOS_EXECUTION_QUEUE_TEST_DATABASE_PASSWORD",""));
        Flyway.configure().dataSource(data).defaultSchema("public").load().migrate();
        String fixture;
        try(var input=Objects.requireNonNull(getClass().getResourceAsStream("/host_runtime_role_hardening.sql"))) {
            fixture=new String(input.readAllBytes(),StandardCharsets.UTF_8);
        }
        try(var connection=data.getConnection()) {
            long before=fixtureRoles(connection);
            connection.setAutoCommit(false);
            try(var statement=connection.createStatement()){statement.execute(fixture);}
            finally {connection.rollback();}
            assertEquals(before,fixtureRoles(connection),"all disposable role changes must roll back");
        }
    }

    private static long fixtureRoles(java.sql.Connection connection) throws java.sql.SQLException {
        try(var statement=connection.createStatement();var rows=statement.executeQuery(
                "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'role_guard_fixture_%' OR rolname LIKE 'role_guard_parent_%'")) {
            rows.next();return rows.getLong(1);
        }
    }
}
