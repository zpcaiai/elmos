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

class JdbcActionCacheIndexTenantScopeTest {

    @Test void aPooledConnectionCannotLeakOneLookupTenantIntoTheNext() {
        var dataSource = new ReusedConnectionDataSource();
        var index = new JdbcActionCacheIndex(dataSource);

        assertTrue(index.find(key("tenant-a")).isEmpty());
        assertNull(dataSource.localTenant);
        assertTrue(dataSource.autoCommit);
        assertTrue(index.find(key("tenant-b")).isEmpty());

        assertEquals(List.of("tenant-a", "tenant-b"), dataSource.queryTenants);
        assertEquals(2, dataSource.commits);
        assertEquals(0, dataSource.rollbacks);
        assertFalse(dataSource.usedSessionScopedSetting);
        assertNull(dataSource.localTenant);
    }

    @Test void anAmbientTransactionIsRefusedRatherThanCommitted() {
        var dataSource = new ReusedConnectionDataSource();
        dataSource.autoCommit = false;
        var index = new JdbcActionCacheIndex(dataSource);

        assertThrows(IllegalStateException.class, () -> index.find(key("tenant-a")));
        assertEquals(0, dataSource.commits);
        assertEquals(0, dataSource.rollbacks);
        assertTrue(dataSource.queryTenants.isEmpty());
    }

    private static ActionKey key(String tenantId) {
        return new ActionKey(CasDigest.ofUtf8(tenantId + ":action"), tenantId,
                java.util.Map.of("tenant_id", tenantId));
    }

    private static final class ReusedConnectionDataSource implements DataSource {
        private final List<String> queryTenants = new ArrayList<>();
        private boolean autoCommit = true;
        private boolean usedSessionScopedSetting;
        private String localTenant;
        private int commits;
        private int rollbacks;
        private final Connection connection = proxy(Connection.class, this::connectionCall);

        private Object connectionCall(Object ignored, java.lang.reflect.Method method, Object[] args)
                throws SQLException {
            return switch (method.getName()) {
                case "getAutoCommit" -> autoCommit;
                case "setAutoCommit" -> {
                    autoCommit = (boolean) args[0];
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
                    localTenant = null;
                    yield null;
                }
                case "close" -> null;
                case "isClosed", "isWrapperFor" -> false;
                case "unwrap" -> throw new SQLFeatureNotSupportedException();
                default -> defaultValue(method.getReturnType());
            };
        }

        private PreparedStatement preparedStatement(String sql) {
            final String[] firstString = new String[1];
            InvocationHandler handler = (ignored, method, args) -> switch (method.getName()) {
                case "setString" -> {
                    if ((int) args[0] == 1) firstString[0] = (String) args[1];
                    yield null;
                }
                case "execute" -> {
                    if (sql.contains("set_config")) {
                        usedSessionScopedSetting = sql.contains(", false)");
                        if (autoCommit || !sql.contains(", true)")) {
                            throw new SQLException("tenant setting is not transaction-local");
                        }
                        localTenant = firstString[0];
                    }
                    yield true;
                }
                case "executeQuery" -> {
                    if (localTenant == null) throw new SQLException("query has no tenant scope");
                    queryTenants.add(localTenant);
                    yield proxy(ResultSet.class, (row, rowMethod, rowArgs) ->
                            "next".equals(rowMethod.getName())
                                    ? false : defaultValue(rowMethod.getReturnType()));
                }
                case "close" -> null;
                default -> defaultValue(method.getReturnType());
            };
            return proxy(PreparedStatement.class, handler);
        }

        @Override public Connection getConnection() { return connection; }
        @Override public Connection getConnection(String username, String password) { return connection; }
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
        return (T) Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[]{type}, handler);
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
