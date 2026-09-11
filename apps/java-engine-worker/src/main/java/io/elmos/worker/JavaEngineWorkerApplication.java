package io.elmos.worker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration;

@SpringBootApplication(exclude = {
        DataSourceAutoConfiguration.class,
        HibernateJpaAutoConfiguration.class,
        org.springframework.boot.actuate.autoconfigure.security.servlet.ManagementWebSecurityAutoConfiguration.class,
        org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class,
        org.springframework.cloud.gateway.config.GatewayClassPathWarningAutoConfiguration.class,
        org.springframework.cloud.gateway.config.GatewayAutoConfiguration.class
})
public class JavaEngineWorkerApplication {
    public static void main(String[] args) { SpringApplication.run(JavaEngineWorkerApplication.class, args); }
}
