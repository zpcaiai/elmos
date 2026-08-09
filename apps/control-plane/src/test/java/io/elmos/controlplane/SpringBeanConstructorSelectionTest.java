package io.elmos.controlplane;

import io.elmos.integrations.GitRepositoryWorkspaceService;
import io.elmos.persistence.JdbcOperationsManagementStore;
import io.elmos.persistence.JdbcUserActivityStore;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import java.time.Clock;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.mock;

class SpringBeanConstructorSelectionTest {
    @Test
    void springSelectsTheProductionNotificationDispatcherConstructor() {
        try (var context = new AnnotationConfigApplicationContext()) {
            TestPropertyValues.of(
                    "elmos.operations.notification-enabled=false",
                    "elmos.operations.notification-webhook-url=",
                    "elmos.operations.notification-hmac-secret-file=",
                    "elmos.operations.organization-id=",
                    "elmos.operations.actor-id="
            ).applyTo(context);
            context.registerBean(JdbcOperationsManagementStore.class,
                    () -> mock(JdbcOperationsManagementStore.class));
            context.registerBean(Clock.class, Clock::systemUTC);
            context.register(OperationsNotificationDispatcher.class);

            assertDoesNotThrow(context::refresh);
            assertNotNull(context.getBean(OperationsNotificationDispatcher.class));
        }
    }

    @Test
    void springSelectsTheProductionRepositoryWorkspaceControllerConstructor() {
        try (var context = new AnnotationConfigApplicationContext()) {
            TestPropertyValues.of(
                    "elmos.repository-workspace.enabled=true",
                    "elmos.repository-workspace.legacy-api-key-enabled=false",
                    "elmos.repository-workspace.legacy-api-key-file=",
                    "elmos.snapshot.materialized-root="
            ).applyTo(context);
            context.registerBean(GitRepositoryWorkspaceService.class,
                    () -> mock(GitRepositoryWorkspaceService.class));
            context.registerBean(RepositoryWorkspaceCredentialStore.class,
                    () -> mock(RepositoryWorkspaceCredentialStore.class));
            context.registerBean(JdbcUserActivityStore.class,
                    () -> mock(JdbcUserActivityStore.class));
            context.registerBean(Clock.class, Clock::systemUTC);
            context.register(RepositoryWorkspaceController.class);

            assertDoesNotThrow(context::refresh);
            assertNotNull(context.getBean(RepositoryWorkspaceController.class));
        }
    }
}
