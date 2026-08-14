package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

/** Disabled-by-default bridge from the authenticated control plane to the database worker. */
@Configuration
class ChinaDbSqlPreflightConfiguration {
    @Bean
    ChinaDbSqlPreflightGateway chinaDbSqlPreflightGateway(
            @Value("${elmos.database-data-preflight.enabled:false}") boolean enabled,
            @Value("${elmos.database-data-preflight.engine-base-url:http://database-data-engine-worker:8089}") String baseUrl,
            @Value("${elmos.database-data-preflight.connect-timeout:2s}") Duration connectTimeout,
            @Value("${elmos.database-data-preflight.request-timeout:20s}") Duration requestTimeout,
            ObjectMapper json
    ) {
        return new HttpChinaDbSqlPreflightGateway(
                enabled, baseUrl, connectTimeout, requestTimeout, json);
    }

    @Bean
    FilterRegistrationBean<ChinaDbSqlPreflightBodyLimitFilter> chinaDbSqlPreflightBodyLimit() {
        var registration = new FilterRegistrationBean<>(new ChinaDbSqlPreflightBodyLimitFilter());
        registration.addUrlPatterns("/api/v1/database-data/sql-preflight/assess");
        registration.setOrder(Integer.MIN_VALUE + 110);
        return registration;
    }
}
