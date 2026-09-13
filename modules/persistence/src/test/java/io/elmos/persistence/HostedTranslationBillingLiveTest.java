package io.elmos.persistence;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** Local disposable PostgreSQL qualification for the V92 commercial boundary. */
class HostedTranslationBillingLiveTest {
    private static DriverManagerDataSource data;

    @BeforeAll static void database() {
        String url=System.getenv("ELMOS_EXECUTION_QUEUE_TEST_JDBC_URL");
        assumeTrue(url!=null&&!url.isBlank(),"requires disposable PostgreSQL");
        if(!"true".equals(System.getenv("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE"))) {
            throw new IllegalStateException("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE=true required");
        }
        data=new DriverManagerDataSource(url,
                System.getenv().getOrDefault(
                        "ELMOS_EXECUTION_QUEUE_TEST_DATABASE_USER",System.getProperty("user.name")),
                System.getenv().getOrDefault("ELMOS_EXECUTION_QUEUE_TEST_DATABASE_PASSWORD",""));
        Flyway.configure().dataSource(data).defaultSchema("public").load().migrate();
    }

    @Test void billingNeedsBothTheSwitchAndOneExactPublishedPrice() throws Exception {
        try(Connection c=data.getConnection()) {
            c.setAutoCommit(false);
            try {
                assertEquals("true",scalar(c,"SELECT elmos_translation_billing_guard()"));
                denied(c,"TRANSLATION_HOSTED_BILLING_NOT_ENABLED",
                        "SELECT elmos_translation_billing_guard(true)");

                execute(c,"""
                    UPDATE wallet_enforcement_settings
                       SET enabled=true,
                           catalog_version='2026-09-08.translation-hosted-v1',
                           updated_by='test:v90',updated_at=now()
                     WHERE singleton
                    """);
                denied(c,"TRANSLATION_HOSTED_BILLING_CONTRACT_REQUIRED",
                        "SELECT elmos_translation_billing_guard(true)");

                String catalog="v90-test-"+UUID.randomUUID();
                execute(c,"""
                    INSERT INTO wallet_price_book(
                        catalog_version,business_line,job_kind,currency,
                        reserve_minor,unit,unit_price_minor,min_charge_minor,
                        effective_from,source_ref,status)
                    VALUES (?,'TRANSLATION','*','CNY',2000,'WALL_SECOND',2,100,
                            now()-interval '1 hour','test:v90','PUBLISHED')
                    """,catalog);
                execute(c,"UPDATE wallet_enforcement_settings SET catalog_version=? WHERE singleton",
                        catalog);
                denied(c,"TRANSLATION_HOSTED_BILLING_CONTRACT_REQUIRED",
                        "SELECT elmos_translation_billing_guard(true)");

                execute(c,"""
                    INSERT INTO wallet_price_book(
                        catalog_version,business_line,job_kind,currency,
                        reserve_minor,unit,unit_price_minor,min_charge_minor,
                        effective_from,source_ref,status)
                    VALUES (?,'TRANSLATION','translate-pipeline-v1','CNY',
                            2000,'WALL_SECOND',2,100,
                            now()-interval '1 hour','test:v90','PUBLISHED')
                    """,catalog);
                assertEquals("true",
                        scalar(c,"SELECT elmos_translation_billing_guard(true)"));
            } finally {c.rollback();}
        }
    }

    @Test void jobBackedUnknownSettlementCannotTurnIntoAFreeTtlRelease() throws Exception {
        try(Connection c=data.getConnection()) {
            c.setAutoCommit(false);
            try {
                String org="v90-wallet-"+UUID.randomUUID();
                execute(c,"INSERT INTO organizations(organization_id) VALUES(?)",org);
                scalar(c,"SELECT elmos_wallet_open(?)",org);
                scalar(c,"SELECT elmos_wallet_adjust(?, 'CREDIT', 10000, 'fixture', "
                        + "'V92 qualification credit', ?)",org,"credit-"+org);
                execute(c,"SELECT set_config('app.organization_id',?,true)",org);
                execute(c,"""
                    INSERT INTO execution_jobs(
                        job_id,organization_id,actor_id,business_line,job_kind,
                        idempotency_key,request_digest,required_capability,request_payload)
                    VALUES ('job-backed',?,'fixture','TRANSLATION',
                            'translate-pipeline-v1','job-backed',repeat('a',64),
                            'translation:multi','{}')
                    """,org);
                scalar(c,"SELECT elmos_wallet_reserve(?,?,?,?,?,?,?)",
                        "res-backed",org,"job-backed",1000,"test:v90","fixture",300);
                execute(c,"""
                    UPDATE wallet_reservations
                       SET held_at=now()-interval '2 hours',
                           expires_at=now()-interval '1 hour'
                     WHERE organization_id=? AND job_id='job-backed'
                    """,org);
                assertEquals("0",scalar(c,
                        "SELECT elmos_wallet_expire_reservations(?,100)",org));
                assertEquals("HELD",scalar(c,"""
                    SELECT status FROM wallet_reservations
                     WHERE organization_id=? AND job_id='job-backed'
                    """,org));

                scalar(c,"SELECT elmos_wallet_reserve(?,?,?,?,?,?,?)",
                        "res-orphan",org,"job-orphan",1000,"test:v90","fixture",300);
                execute(c,"""
                    UPDATE wallet_reservations
                       SET held_at=now()-interval '2 hours',
                           expires_at=now()-interval '1 hour'
                     WHERE organization_id=? AND job_id='job-orphan'
                    """,org);
                assertEquals("1",scalar(c,
                        "SELECT elmos_wallet_expire_reservations(?,100)",org));
                assertEquals("EXPIRED",scalar(c,"""
                    SELECT status FROM wallet_reservations
                     WHERE organization_id=? AND job_id='job-orphan'
                    """,org));
            } finally {c.rollback();}
        }
    }

    private static void denied(Connection c,String code,String sql,Object...args)
            throws SQLException {
        var savepoint=c.setSavepoint();
        try {
            SQLException error=assertThrows(SQLException.class,()->scalar(c,sql,args));
            assertTrue(error.getMessage().contains(code),error.getMessage());
        } finally {c.rollback(savepoint);}
    }

    private static void execute(Connection c,String sql,Object...args) throws SQLException {
        try(var p=c.prepareStatement(sql)) {
            for(int i=0;i<args.length;i++) p.setObject(i+1,args[i]);
            p.execute();
        }
    }

    private static String scalar(Connection c,String sql,Object...args) throws SQLException {
        try(var p=c.prepareStatement(sql)) {
            for(int i=0;i<args.length;i++) p.setObject(i+1,args[i]);
            try(var r=p.executeQuery()) {
                assertTrue(r.next());
                return String.valueOf(r.getObject(1));
            }
        }
    }
}
