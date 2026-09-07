package io.elmos.persistence;

import org.aopalliance.intercept.MethodInterceptor;
import org.junit.jupiter.api.Test;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor;
import org.springframework.core.type.filter.AnnotationTypeFilter;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;

import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RepositoryProxyCompatibilityTest {
    @Test
    void everyRepositorySupportsTheClassProxyUsedBySpringBoot() {
        var scanner = new ClassPathScanningCandidateComponentProvider(false);
        scanner.addIncludeFilter(new AnnotationTypeFilter(Repository.class));
        List<Class<?>> repositories = scanner.findCandidateComponents("io.elmos.persistence").stream()
                .map(BeanDefinition::getBeanClassName)
                .map(RepositoryProxyCompatibilityTest::loadClass)
                .toList();

        assertFalse(repositories.isEmpty(), "repository scan must not pass vacuously");
        repositories.forEach(type -> {
            assertDoesNotThrow(
                    () -> createClassProxy(type),
                    () -> type.getName() + " must support Spring's default class-based proxy");
            if (type.getDeclaredConstructors().length > 1) {
                long autowired = Arrays.stream(type.getDeclaredConstructors())
                        .filter(constructor -> constructor.isAnnotationPresent(
                                org.springframework.beans.factory.annotation.Autowired.class))
                        .count();
                assertEquals(1, autowired,
                        () -> type.getName() + " must identify exactly one production constructor");
            }
        });
    }

    @Test
    void workspaceLifecycleTransactionsRemainClassProxyCompatible() {
        assertTrue(Arrays.stream(JdbcWorkspaceLifecycleStore.class.getDeclaredMethods())
                        .anyMatch(method -> method.isAnnotationPresent(Transactional.class)),
                "workspace lifecycle writes must remain transaction-managed");
        assertFalse(Modifier.isFinal(JdbcWorkspaceLifecycleStore.class.getModifiers()),
                "transaction-managed workspace lifecycle bean must be subclassable");
        assertDoesNotThrow(() -> createClassProxy(JdbcWorkspaceLifecycleStore.class));
    }

    @Test
    void springCreatesAndClassProxiesTheMultiConstructorRunHistoryRepository() {
        var dataSource = new DriverManagerDataSource();
        dataSource.setUrl("jdbc:postgresql://127.0.0.1:1/not-used");
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(JdbcClient.class, () -> JdbcClient.create(dataSource));
            context.registerBean(PlatformTransactionManager.class,
                    () -> new DataSourceTransactionManager(dataSource));
            context.registerBean(PersistenceExceptionTranslationPostProcessor.class, () -> {
                var processor = new PersistenceExceptionTranslationPostProcessor();
                processor.setProxyTargetClass(true);
                return processor;
            });
            context.register(JdbcRunHistoryStore.class);

            assertDoesNotThrow(context::refresh);
            assertTrue(AopUtils.isCglibProxy(context.getBean(JdbcRunHistoryStore.class)),
                    "the real Spring repository post-processor must create a class proxy");
        }
    }

    private static Class<?> loadClass(String name) {
        try {
            return Class.forName(name);
        } catch (ClassNotFoundException error) {
            throw new AssertionError("Unable to load repository " + name, error);
        }
    }

    private static Object createClassProxy(Class<?> targetType) {
        var factory = new ProxyFactory();
        factory.setTargetClass(targetType);
        factory.setProxyTargetClass(true);
        factory.addAdvice((MethodInterceptor) invocation -> invocation.proceed());
        return factory.getProxy();
    }
}
