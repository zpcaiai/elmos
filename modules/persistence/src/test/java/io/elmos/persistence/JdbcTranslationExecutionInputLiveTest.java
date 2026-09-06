package io.elmos.persistence;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** Real PostgreSQL checks; requires an explicitly acknowledged disposable database. */
class JdbcTranslationExecutionInputLiveTest {
    static JdbcClient jdbc;
    static TransactionTemplate transactions;

    @BeforeAll static void database() {
        String url = System.getenv("ELMOS_EXECUTION_QUEUE_TEST_JDBC_URL");
        assumeTrue(url != null && !url.isBlank(), "requires a disposable PostgreSQL fixture");
        if (!"true".equals(System.getenv("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE")))
            throw new IllegalStateException("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE=true required");
        var data = new DriverManagerDataSource(url,
                System.getenv().getOrDefault("ELMOS_EXECUTION_QUEUE_TEST_DATABASE_USER", System.getProperty("user.name")),
                System.getenv().getOrDefault("ELMOS_EXECUTION_QUEUE_TEST_DATABASE_PASSWORD", ""));
        Flyway.configure().dataSource(data).defaultSchema("public").load().migrate();
        jdbc = JdbcClient.create(data);
        transactions = new TransactionTemplate(new DataSourceTransactionManager(data));
    }

    @Test void expiredPreparedInputDoesNotAssumeAnUnknownPutHasStopped() {
        String org = tenant(); String object = object(org, 1); String binding = prepare(org, object, "same", 1);
        jdbc.sql("UPDATE execution_input_bindings SET prepared_expires_at = now() - interval '1 day' WHERE binding_id = :id")
                .param("id", binding).update();
        gc();
        assertEquals("AVAILABLE", state(object));
        assertTrue(retained(object));
        assertEquals(binding, prepare(org, object, "same", 1), "retry renews exact binding, not a second root");
    }

    @Test void digestTenantAndIdempotencyDriftCannotAttachAnotherObject() {
        String org = tenant(); String other = tenant(); String object = object(org, 2);
        prepare(org, object, "key", 2);
        assertThrows(RuntimeException.class, () -> prepare(other, object, "key", 2));
        assertThrows(RuntimeException.class, () -> prepare(org, object, "key", 3));
        String next = object(org, 3);
        assertThrows(RuntimeException.class, () -> prepare(org, next, "key", 3));
        assertEquals(1L, jdbc.sql("SELECT count(*) FROM execution_input_bindings WHERE organization_id = :org")
                .param("org", org).query(Long.class).single());
    }

    @Test void attachedInputLivesThroughRunningAndTerminalRetentionThenBecomesPurgeable() {
        String org = tenant(); String object = object(org, 4); String binding = prepare(org, object, "key", 4);
        String job = "job-" + UUID.randomUUID();
        jdbc.sql("""
            INSERT INTO execution_jobs(job_id,organization_id,actor_id,business_line,job_kind,idempotency_key,
              request_digest,required_capability,request_payload)
            VALUES (:job,:org,'fixture','TRANSLATION','translate-pipeline-v1',:job,:sha,'translation:multi',
              jsonb_build_object('input',jsonb_build_object('bindingId',CAST(:binding AS text),'objectId',CAST(:object AS text),
                'sha256',CAST(:sha AS text),'byteSize',CAST(100 AS bigint))))
            """).param("job", job).param("org", org).param("binding", binding).param("object", object).param("sha", digest(4)).update();
        assertEquals(Boolean.TRUE, transactions.execute(status -> {
            bind(org);
            return jdbc.sql("SELECT elmos_attach_execution_input(:org,:job,:binding)")
                    .param("org",org).param("job",job).param("binding",binding).query(Boolean.class).single();
        }));
        gc(); assertEquals("AVAILABLE", state(object));
        jdbc.sql("UPDATE execution_jobs SET status='CANCELLED',finished_at=now() WHERE job_id=:job").param("job",job).update();
        gc(); assertEquals("AVAILABLE", state(object));
        jdbc.sql("UPDATE execution_jobs SET finished_at=now()-interval '3651 days' WHERE job_id=:job").param("job",job).update();
        gc(); assertEquals("PURGE_PENDING", state(object));
        assertThrows(RuntimeException.class, () -> prepare(org,object,"key",4), "purge decision cannot be resurrected");
    }

    @Test void unresolvedPreparationHasAFiniteTenantBudget() {
        String org = tenant();
        for (int i=10;i<18;i++) prepare(org,object(org,i),"key-"+i,i);
        String extra = object(org,18);
        assertThrows(RuntimeException.class, () -> prepare(org,extra,"overflow",18));
        assertEquals(8L,jdbc.sql("SELECT count(*) FROM execution_input_bindings WHERE organization_id=:org")
                .param("org",org).query(Long.class).single());
    }

    static String tenant() {
        String org="org-v86-"+UUID.randomUUID();
        jdbc.sql("INSERT INTO organizations(organization_id) VALUES(:org)").param("org",org).update(); return org;
    }
    static String digest(int n) { return String.format("%064x", n); }
    static String object(String org,int n) {
        String id="obj-"+UUID.randomUUID();
        jdbc.sql("""
            INSERT INTO content_objects(content_object_id,organization_id,content_sha256,byte_size,backend_id,storage_key,
              object_state,uploaded_at,verified_at) VALUES(:id,:org,:sha,100,'primary',:id,'AVAILABLE',now(),now())
            """).param("id",id).param("org",org).param("sha",digest(n)).update(); return id;
    }
    static void bind(String org) {
        jdbc.sql("SELECT set_config('app.organization_id',:org,true)").param("org",org).query(String.class).single();
    }
    static String prepare(String org,String object,String key,int n) {
        return transactions.execute(status -> {
            bind(org);
            return jdbc.sql("SELECT elmos_prepare_execution_input(:id,:org,:key,:object,:sha,CAST(100 AS bigint))")
                    .param("id","input-"+UUID.randomUUID()).param("org",org).param("key",key)
                    .param("object",object).param("sha",digest(n)).query(String.class).single();
        });
    }
    static boolean retained(String object) {
        return jdbc.sql("SELECT elmos_execution_input_retained(:object)").param("object",object).query(Boolean.class).single();
    }
    static String state(String object) {
        return jdbc.sql("SELECT object_state FROM content_objects WHERE content_object_id=:object")
                .param("object",object).query(String.class).single();
    }
    static void gc() {
        jdbc.sql("SELECT elmos_expire_artifacts(:id,5000)").param("id","gc-"+UUID.randomUUID()).query(Integer.class).single();
    }
}
