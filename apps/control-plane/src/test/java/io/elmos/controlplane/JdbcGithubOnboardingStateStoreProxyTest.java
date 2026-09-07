package io.elmos.controlplane;

import org.aopalliance.intercept.MethodInterceptor;
import org.junit.jupiter.api.Test;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.transaction.annotation.Transactional;

import java.lang.reflect.Modifier;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JdbcGithubOnboardingStateStoreProxyTest {
    @Test
    void onboardingTransactionsRemainClassProxyCompatible() {
        assertTrue(Arrays.stream(JdbcGithubOnboardingStateStore.class.getDeclaredMethods())
                        .anyMatch(method -> method.isAnnotationPresent(Transactional.class)),
                "GitHub onboarding state changes must remain transaction-managed");
        assertFalse(Modifier.isFinal(JdbcGithubOnboardingStateStore.class.getModifiers()),
                "transaction-managed onboarding store must be subclassable");

        var factory = new ProxyFactory();
        factory.setTargetClass(JdbcGithubOnboardingStateStore.class);
        factory.setProxyTargetClass(true);
        factory.addAdvice((MethodInterceptor) invocation -> invocation.proceed());
        assertDoesNotThrow(() -> {
            factory.getProxy();
        });
    }
}
