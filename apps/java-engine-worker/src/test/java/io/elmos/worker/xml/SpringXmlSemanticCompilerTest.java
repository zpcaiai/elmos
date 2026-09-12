package io.elmos.worker.xml;

import io.elmos.worker.xml.SpringXmlSemanticCompiler.SemanticCompilationReport;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SpringXmlSemanticCompilerTest {

    @Test
    void testBasicBeansAndNamespaceCompilation() throws Exception {
        String xml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:context="http://www.springframework.org/schema/context"
                       xmlns:tx="http://www.springframework.org/schema/tx"
                       xmlns:aop="http://www.springframework.org/schema/aop"
                       xsi:schemaLocation="http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd">

                    <context:component-scan base-package="com.enterprise.app" />
                    <tx:annotation-driven />
                    <aop:aspectj-autoproxy proxy-target-class="true" />

                    <bean id="orderRepository" class="com.enterprise.app.repository.OrderRepository" />

                    <bean id="orderService" class="com.enterprise.app.service.OrderService"
                          init-method="init" destroy-method="cleanup" primary="true">
                        <constructor-arg ref="orderRepository" />
                        <property name="timeout" value="5000" />
                    </bean>

                </beans>
                """;

        SpringXmlSemanticCompiler compiler = new SpringXmlSemanticCompiler();
        SemanticCompilationReport report = compiler.compileContent(xml, "applicationContext.xml", "com.enterprise.app.config");

        assertTrue(report.isSuccessful());
        assertEquals(2, report.totalBeansCount());
        assertEquals("ApplicationContextConfig", report.targetClassName());

        String java = report.generatedSource();
        assertTrue(java.contains("@Configuration"));
        assertTrue(java.contains("@ComponentScan(basePackages = \"com.enterprise.app\")"));
        assertTrue(java.contains("@EnableTransactionManagement"));
        assertTrue(java.contains("@EnableAspectJAutoProxy(proxyTargetClass = true)"));

        // Topological order check: orderRepository must precede orderService
        int idxRepo = report.topologicalOrder().indexOf("orderRepository");
        int idxService = report.topologicalOrder().indexOf("orderService");
        assertTrue(idxRepo != -1 && idxService != -1);
        assertTrue(idxRepo < idxService, "orderRepository must be initialized before orderService");

        // Code assertions
        assertTrue(java.contains("public OrderRepository orderRepository()"));
        assertTrue(java.contains("public OrderService orderService(OrderRepository orderRepository)"));
        assertTrue(java.contains("initMethod = \"init\""));
        assertTrue(java.contains("@Primary"));
    }

    @Test
    void testCircularDependencyResolution() throws Exception {
        String xml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">

                    <bean id="serviceA" class="com.example.ServiceA">
                        <property name="serviceB" ref="serviceB" />
                    </bean>

                    <bean id="serviceB" class="com.example.ServiceB">
                        <property name="serviceA" ref="serviceA" />
                    </bean>

                </beans>
                """;

        SpringXmlSemanticCompiler compiler = new SpringXmlSemanticCompiler();
        SemanticCompilationReport report = compiler.compileContent(xml, "circularBeans.xml", "com.example.config");

        assertTrue(report.isSuccessful());
        assertEquals(2, report.totalBeansCount());
        assertFalse(report.detectedCycles().isEmpty(), "Circular dependency should be detected");
        assertFalse(report.lazyBeanIds().isEmpty(), "Circular dependency should produce lazy candidate");

        String java = report.generatedSource();
        assertTrue(java.contains("@Lazy"));
    }
}
