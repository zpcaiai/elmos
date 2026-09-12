package io.elmos.worker.xml;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringXmlToJavaConfigConverterTest {

    @TempDir
    Path tempDir;

    @Test
    void convertsSpringBeansXmlToJavaConfig() throws Exception {
        Path xmlFile = tempDir.resolve("applicationContext.xml");
        String xml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:context="http://www.springframework.org/schema/context"
                       xmlns:tx="http://www.springframework.org/schema/tx"
                       xsi:schemaLocation="
                           http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd
                           http://www.springframework.org/schema/context http://www.springframework.org/schema/context/spring-context.xsd
                           http://www.springframework.org/schema/tx http://www.springframework.org/schema/tx/spring-tx.xsd">

                    <context:component-scan base-package="com.example.service" />
                    <context:property-placeholder location="classpath:app.properties" />
                    <tx:annotation-driven />

                    <bean id="orderService" class="com.example.service.OrderService" init-method="init">
                        <property name="timeout" value="5000" />
                        <property name="paymentGateway" ref="paymentGateway" />
                    </bean>

                    <bean id="paymentGateway" class="com.example.service.PaymentGateway" />
                </beans>
                """;
        Files.writeString(xmlFile, xml);

        var config = SpringXmlToJavaConfigConverter.convertXmlFile(xmlFile, "com.example.config");
        assertNotNull(config);
        assertEquals("ApplicationContextConfig", config.configClassName());
        assertEquals(2, config.beansCount());
        assertTrue(config.hasTransactionManagement());
        assertEquals(List.of("com.example.service"), config.componentScans());
        assertEquals(List.of("classpath:app.properties"), config.propertySources());

        String java = config.generatedJavaSource();
        assertTrue(java.contains("@Configuration"));
        assertTrue(java.contains("@ComponentScan(basePackages = {\"com.example.service\"})"));
        assertTrue(java.contains("@PropertySource(\"classpath:app.properties\")"));
        assertTrue(java.contains("@EnableTransactionManagement"));
        assertTrue(java.contains("public com.example.service.OrderService orderService"));
        assertTrue(java.contains("public com.example.service.PaymentGateway paymentGateway"));
        assertTrue(java.contains("initMethod = \"init\""));

        // Test project-level conversion
        Path projectRoot = tempDir.resolve("proj");
        Files.createDirectories(projectRoot.resolve("src/main/resources"));
        Files.writeString(projectRoot.resolve("src/main/resources/beans.xml"), xml);

        var projRes = SpringXmlToJavaConfigConverter.convertProject(projectRoot, "com.example.config");
        assertTrue(projRes.converted());
        assertEquals(1, projRes.xmlFilesConverted());
        assertEquals(2, projRes.totalBeansConverted());
        assertTrue(Files.exists(projectRoot.resolve("src/main/java/com/example/config/BeansConfig.java")));
    }

    @Test
    void convertsNestedRefAndPNamespaceBeans() throws Exception {
        Path xmlFile = tempDir.resolve("complexBeans.xml");
        String xml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:p="http://www.springframework.org/schema/p"
                       xmlns:c="http://www.springframework.org/schema/c">

                    <bean id="dataSource" class="com.example.db.DataSource" p:url="jdbc:postgresql://localhost/db" />

                    <bean id="accountDao" class="com.example.dao.AccountDao" p:dataSource-ref="dataSource">
                        <property name="driver">
                            <value>org.postgresql.Driver</value>
                        </property>
                        <property name="secondarySource">
                            <ref bean="dataSource" />
                        </property>
                    </bean>

                    <bean id="accountService" class="com.example.service.AccountService"
                          primary="true" lazy-init="true">
                        <constructor-arg>
                            <ref bean="accountDao" />
                        </constructor-arg>
                    </bean>
                </beans>
                """;
        Files.writeString(xmlFile, xml);

        var config = SpringXmlToJavaConfigConverter.convertXmlFile(xmlFile, "com.example.config");
        assertNotNull(config);
        assertEquals("ComplexBeansConfig", config.configClassName());
        assertEquals(3, config.beansCount());

        String java = config.generatedJavaSource();
        assertTrue(java.contains("@Configuration"));
        assertTrue(java.contains("@Primary"));
        assertTrue(java.contains("@Lazy"));
        assertTrue(java.contains("public com.example.db.DataSource dataSource"));
        assertTrue(java.contains("public com.example.dao.AccountDao accountDao"));
        assertTrue(java.contains("public com.example.service.AccountService accountService"));

        // Topological ordering check: dataSource must appear before accountDao, and accountDao before accountService
        int idxDs = java.indexOf("dataSource(");
        int idxDao = java.indexOf("accountDao(");
        int idxService = java.indexOf("accountService(");
        assertTrue(idxDs < idxDao, "dataSource must be emitted before accountDao in topological order");
        assertTrue(idxDao < idxService, "accountDao must be emitted before accountService in topological order");
    }
}
