package io.elmos.databasedata;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

/** Disabled-by-default wiring for the fixed ChinaDB SQL preflight sidecar. */
@Configuration
class ChinaDbSqlPreflightConfiguration {
    @Bean
    ChinaDbSqlPreflightGateway chinaDbSqlPreflightGateway(
            @Value("${elmos.chinadb-sql-preflight.enabled:false}") boolean enabled,
            @Value("${elmos.chinadb-sql-preflight.base-url:http://chinadb-sql-preflight:8101}") String baseUrl,
            @Value("${elmos.chinadb-sql-preflight.connect-timeout:2s}") Duration connectTimeout,
            @Value("${elmos.chinadb-sql-preflight.request-timeout:15s}") Duration requestTimeout,
            ObjectMapper json
    ) {
        return new HttpChinaDbSqlPreflightGateway(
                enabled, baseUrl, connectTimeout, requestTimeout, json);
    }

    @Bean
    FilterRegistrationBean<ChinaDbSqlPreflightBodyLimitFilter> chinaDbSqlPreflightBodyLimit(
            ObjectMapper json
    ) {
        var registration = new FilterRegistrationBean<>(new ChinaDbSqlPreflightBodyLimitFilter(json));
        registration.addUrlPatterns("/engine/v1/sql-preflight/assess");
        registration.setOrder(Integer.MIN_VALUE + 110);
        return registration;
    }
}
