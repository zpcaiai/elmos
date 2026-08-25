package io.elmos.cas;

import org.junit.jupiter.api.Test;

import javax.sql.DataSource;
import java.io.PrintWriter;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JdbcCasCatalogTenantScopeTest {

    @Test
    void aReusedPooledConnectionNeverCarriesThePreviousTenantIntoTheNextBorrower() {
        var dataSource = new ReusedConnectionDataSource();
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest digest = CasDigest.ofUtf8("same global digest");

        assertTrue(catalog.find("tenant-a", digest).isEmpty());
        assertNull(dataSource.localTenant,
                "commit must clear the transaction-local tenant before pool return");
        assertTrue(dataSource.autoCommit,
                "the connection must be restored before another component borrows it");

        assertTrue(catalog.find("tenant-b", digest).isEmpty());

        assertEquals(List.of("tenant-a", "tenant-b"), dataSource.queryTenants);
        assertEquals(2, dataSource.commits);
        assertEquals(0, dataSource.rollbacks);
        assertNull(dataSource.localTenant);
        assertTrue(dataSource.autoCommit);
        assertFalse(dataSource.usedSessionScopedSetting,
                "set_config(..., false) would leak tenant state through the pool");
    }

    @Test
    void anAmbientTransactionIsRefusedRatherThanCommittedByTheCatalogue() {
        var dataSource = new ReusedConnectionDataSource();
        dataSource.autoCommit = false;
        var catalog = new JdbcCasCatalog(dataSource);

        assertThrows(IllegalStateException.class,
                () -> catalog.find("tenant-a", CasDigest.ofUtf8("payload")));
        assertEquals(0, dataSource.commits);
        assertEquals(0, dataSource.rollbacks);
        assertTrue(dataSource.queryTenants.isEmpty());
    }

    @Test
    void aRollbackFailureAbortsTheConnectionWithoutRestoringAutoCommit() {
        var dataSource = new ReusedConnectionDataSource();
        dataSource.failQueries = true;
        dataSource.failRollback = true;
        var catalog = new JdbcCasCatalog(dataSource);

        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> catalog.find("tenant-a", CasDigest.ofUtf8("payload")));

        assertEquals(1, dataSource.rollbacks);
        assertEquals(1, dataSource.aborts);
        assertFalse(dataSource.autoCommit,
                "an unresolved transaction must never be committed by restoring auto-commit");
        assertEquals(0, dataSource.autoCommitRestores);
        assertTrue(failure.getCause().getSuppressed().length >= 1,
                "the rollback failure must remain attached to the operation failure");
    }

    private static final class ReusedConnectionDataSource implements DataSource {
        private final List<String> queryTenants = new ArrayList<>();
        private boolean autoCommit = true;
        private boolean usedSessionScopedSetting;
        private String localTenant;
        private int commits;
        private int rollbacks;
        private int aborts;
        private int autoCommitRestores;
        private boolean failQueries;
        private boolean failRollback;
        private final Connection connection = proxy(Connection.class, this::connectionCall);

        private Object connectionCall(Object ignored, java.lang.reflect.Method method, Object[] args)
                throws SQLException {
            return switch (method.getName()) {
                case "getAutoCommit" -> autoCommit;
                case "setAutoCommit" -> {
                    autoCommit = (boolean) args[0];
                    if (autoCommit) autoCommitRestores++;
                    yield null;
                }
                case "prepareStatement" -> preparedStatement((String) args[0]);
                case "commit" -> {
                    commits++;
                    localTenant = null;
                    yield null;
                }
                case "rollback" -> {
                    rollbacks++;
                    if (failRollback) throw new SQLException("rollback failed");
                    localTenant = null;
                    yield null;
                }
                case "abort" -> {
                    aborts++;
                    localTenant = null;
                    yield null;
                }
                case "close" -> null; // Simulates returning the same physical connection.
                case "isClosed" -> false;
                case "isWrapperFor" -> false;
                case "unwrap" -> throw new SQLFeatureNotSupportedException();
                case "toString" -> "reused-test-connection";
                default -> defaultValue(method.getReturnType());
            };
        }

        private PreparedStatement preparedStatement(String sql) {
            final String[] tenantParameter = new String[1];
            InvocationHandler handler = (ignored, method, args) -> switch (method.getName()) {
                case "setString" -> {
                    if ((int) args[0] == 1) {
                        tenantParameter[0] = (String) args[1];
                    }
                    yield null;
                }
                case "execute" -> {
                    if (sql.contains("set_config")) {
                        usedSessionScopedSetting = sql.contains(", false)");
                        if (autoCommit || !sql.contains(", true)")) {
                            throw new SQLException(
                                    "tenant setting was not transaction-local inside a transaction");
                        }
                        localTenant = tenantParameter[0];
                    }
                    yield true;
                }
                case "executeQuery" -> {
                    if (localTenant == null) {
                        throw new SQLException("query executed without a tenant-local scope");
                    }
                    if (failQueries) throw new SQLException("query failed");
                    queryTenants.add(localTenant);
                    yield proxy(ResultSet.class, (row, rowMethod, rowArgs) ->
                            "next".equals(rowMethod.getName())
                                    ? false : defaultValue(rowMethod.getReturnType()));
                }
                case "close" -> null;
                case "toString" -> sql;
                default -> defaultValue(method.getReturnType());
            };
            return proxy(PreparedStatement.class, handler);
        }

        @Override
        public Connection getConnection() {
            return connection;
        }

        @Override
        public Connection getConnection(String username, String password) {
            return connection;
        }

        @Override public PrintWriter getLogWriter() { return null; }
        @Override public void setLogWriter(PrintWriter out) { }
        @Override public void setLoginTimeout(int seconds) { }
        @Override public int getLoginTimeout() { return 0; }
        @Override public Logger getParentLogger() { return Logger.getGlobal(); }
        @Override public <T> T unwrap(Class<T> iface) throws SQLException {
            throw new SQLFeatureNotSupportedException();
        }
        @Override public boolean isWrapperFor(Class<?> iface) { return false; }
    }

    @SuppressWarnings("unchecked")
    private static <T> T proxy(Class<T> type, InvocationHandler handler) {
        return (T) Proxy.newProxyInstance(
                type.getClassLoader(), new Class<?>[]{type}, handler);
    }

    private static Object defaultValue(Class<?> type) {
        if (!type.isPrimitive() || type == void.class) return null;
        if (type == boolean.class) return false;
        if (type == byte.class) return (byte) 0;
        if (type == short.class) return (short) 0;
        if (type == int.class) return 0;
        if (type == long.class) return 0L;
        if (type == float.class) return 0F;
        if (type == double.class) return 0D;
        if (type == char.class) return '\0';
        throw new IllegalArgumentException("unsupported primitive " + type);
    }
}
