package io.elmos.persistence;

import io.elmos.storage.S3ObjectStore;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DelegatingDataSource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** Local PG only. Owner/role changes and bulk fixtures roll back, including on assertion failure. */
class JdbcTenantObjectRetentionLiveTest {
    static DriverManagerDataSource data;
    static final String PREPARE="elmos_object_gc_host_prepare(varchar,integer,integer,integer)";
    static final String CONFIRM="elmos_object_gc_host_confirm(varchar,varchar,varchar,varchar,varchar,varchar,varchar,varchar,bigint)";
    static final String UNKNOWN="elmos_object_gc_host_unknown(varchar,varchar)";

    @BeforeAll static void database() {
        String url=System.getenv("ELMOS_EXECUTION_QUEUE_TEST_JDBC_URL");
        assumeTrue(url!=null&&!url.isBlank(),"requires disposable PostgreSQL");
        if(!"true".equals(System.getenv("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE")))
            throw new IllegalStateException("ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE=true required");
        data=new DriverManagerDataSource(url,
                System.getenv().getOrDefault("ELMOS_EXECUTION_QUEUE_TEST_DATABASE_USER",System.getProperty("user.name")),
                System.getenv().getOrDefault("ELMOS_EXECUTION_QUEUE_TEST_DATABASE_PASSWORD",""));
        Flyway.configure().dataSource(data).defaultSchema("public").load().migrate();
    }

    @Test void ordinaryOwnerHonorsForcedRlsAndRestoresContext() throws Exception { ownerTuple(true); }
    @Test void privilegedOwnerStillUsesExactTenantPredicates() throws Exception { ownerTuple(false); }

    private void ownerTuple(boolean ordinary) throws Exception {
        try(Connection c=data.getConnection()) {
            c.setAutoCommit(false);
            try {
                String prefix=prefix(),a=prefix+"a",b=prefix+"b";
                tenant(c,a);tenant(c,b);objects(c,a,2);objects(c,b,1);cursor(c,prefix);
                scalar(c,"SELECT set_config('app.organization_id',?,true)",a);
                scalar(c,"SELECT elmos_prepare_execution_input(?,?,?,?,?,CAST(100 AS bigint))",prefix+"input",a,"unknown-input",a+"-o2",String.format("%064x",2));
                execute(c,"UPDATE execution_input_bindings SET prepared_expires_at=now()-interval '100 years' WHERE binding_id=?",prefix+"input");
                if(ordinary) {
                    String owner="gch_owner_"+UUID.randomUUID().toString().replace("-","");
                    execute(c,"CREATE ROLE "+owner+" NOLOGIN NOSUPERUSER NOBYPASSRLS");
                    execute(c,"GRANT USAGE ON SCHEMA public TO "+owner);
                    execute(c,"GRANT SELECT,INSERT,UPDATE,DELETE ON object_gc_host_cursor,object_gc_host_runs,object_gc_host_items TO "+owner);
                    execute(c,"GRANT SELECT ON organizations,execution_input_bindings,execution_jobs TO "+owner);
                    execute(c,"GRANT SELECT,INSERT,UPDATE ON content_objects,job_artifacts,object_gc_runs TO "+owner);
                    for(String f:List.of(PREPARE,CONFIRM,UNKNOWN,"elmos_expire_artifacts(varchar,integer)",
                            "elmos_execution_input_retained(varchar)","elmos_confirm_object_purged(varchar,varchar)",
                            "elmos_finish_object_gc(varchar,integer,integer)")) {
                        execute(c,"GRANT EXECUTE ON FUNCTION "+f+" TO "+owner);
                        execute(c,"ALTER FUNCTION "+f+" OWNER TO "+owner);
                    }
                    execute(c,"SET LOCAL ROLE "+owner);
                    assertEquals("true",scalar(c,"SELECT row_security_active('content_objects')"));
                    execute(c,"RESET ROLE");
                }
                String tenantRole="gch_tenant_"+UUID.randomUUID().toString().replace("-","");
                execute(c,"CREATE ROLE "+tenantRole+" NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT");
                execute(c,"GRANT USAGE ON SCHEMA public TO "+tenantRole);
                execute(c,"GRANT SELECT ON content_objects TO "+tenantRole);
                execute(c,"SET LOCAL ROLE "+tenantRole);
                scalar(c,"SELECT set_config('app.organization_id',?,true)",b);
                assertEquals("1",scalar(c,"SELECT count(*) FROM content_objects"),"ordinary tenant retains row isolation");
                assertEquals("false",scalar(c,"SELECT has_function_privilege(current_user,?,'EXECUTE')",PREPARE));
                denied(c,"permission denied","SELECT * FROM "+PREPARE.substring(0,PREPARE.indexOf('('))+"('denied',1,1,1)");
                execute(c,"SET LOCAL ROLE elmos_object_gc_host");
                assertEquals("false",scalar(c,"SELECT rolinherit FROM pg_roles WHERE rolname=current_user"));
                assertEquals("false",scalar(c,"SELECT has_table_privilege(current_user,'object_gc_host_runs','SELECT')"));
                scalar(c,"SELECT set_config('app.organization_id',?,true)",b);
                var first=prepare(c,1,10,10);
                assertEquals(1,first.size()); assertEquals(a,first.getFirst().organizationId());
                assertEquals(b,scalar(c,"SELECT current_setting('app.organization_id')"));
                assertEquals("true",confirm(c,first.getFirst()));
                assertEquals(b,scalar(c,"SELECT current_setting('app.organization_id')"));
                execute(c,"RESET ROLE");
                assertEquals("PURGED",state(c,a+"-o1")); assertEquals("AVAILABLE",state(c,b+"-o1"));
                assertEquals("AVAILABLE",state(c,a+"-o2"),"expired PREPARED input must remain rooted under either function owner");
                execute(c,"SET LOCAL ROLE elmos_object_gc_host");
                assertEquals(b,prepare(c,1,1,1).getFirst().organizationId());
            } finally {c.rollback();}
        }
    }

    @Test void oneRoundHasTotalBudgetsAndRotatesBeyondEightTenants() throws Exception {
        try(Connection c=data.getConnection()) {
            c.setAutoCommit(false);
            try {
                String prefix=prefix();
                for(int n=0;n<9;n++){String org=prefix+n;tenant(c,org);objects(c,org,40);artifacts(c,org,40);}
                cursor(c,prefix);
                var first=prepare(c,8,256,128);
                assertEquals(128,first.size());assertEquals(8,first.stream().map(JdbcTenantObjectRetentionStore.Purge::organizationId).distinct().count());
                assertEquals("256",scalar(c,"SELECT count(*) FROM job_artifacts WHERE organization_id LIKE ? AND deleted_at IS NOT NULL",prefix+"%"));
                assertEquals("256",scalar(c,"SELECT count(*) FROM content_objects WHERE organization_id LIKE ? AND object_state='PURGE_PENDING'",prefix+"%"));
                assertEquals("0",scalar(c,"SELECT count(*) FROM content_objects WHERE organization_id=? AND object_state='PURGE_PENDING'",prefix+8));
                var next=prepare(c,8,256,128);
                assertTrue(next.stream().anyMatch(p->p.organizationId().equals(prefix+8)),"ninth tenant must get the next round");
                assertTrue(next.size()<=128);
                denied(c,"ELMOS_OBJECT_GC_HOST_BUDGET_INVALID","SELECT * FROM elmos_object_gc_host_prepare('oversize',9,256,128)");
                denied(c,"ELMOS_OBJECT_GC_HOST_BUDGET_INVALID","SELECT * FROM elmos_object_gc_host_prepare('oversize',8,257,128)");
                denied(c,"ELMOS_OBJECT_GC_HOST_BUDGET_INVALID","SELECT * FROM elmos_object_gc_host_prepare('oversize',8,256,129)");
            } finally {c.rollback();}
        }
    }

    @Test void unknownRetryReusesExactItemAndCannotDowngradeConfirmation() throws Exception {
        try(Connection c=data.getConnection()) {
            c.setAutoCommit(false);
            try {
                String prefix=prefix(),org=prefix+"a";tenant(c,org);objects(c,org,1);cursor(c,prefix);
                var item=prepare(c,1,1,1).getFirst();
                scalar(c,"SELECT elmos_object_gc_host_unknown(?,?)",item.runId(),item.contentObjectId());
                execute(c,"UPDATE object_gc_host_runs SET created_at=now()-interval '100 years' WHERE run_id=?",item.runId());
                cursor(c,prefix);
                assertEquals(item,prepare(c,1,1,1).getFirst(),"age is not evidence of provider termination");
                assertEquals("PURGE_PENDING",state(c,item.contentObjectId()));
                denied(c,"ELMOS_OBJECT_GC_HOST_BINDING_MISMATCH",
                        "SELECT elmos_object_gc_host_confirm(?,?,?,?,?,?,?,?,?)",
                        item.runId(),item.contentObjectId(),org,item.contentSha256(),
                        "wrong-backend",item.storageKey(),"request",
                        "d835c506a9a8f23ea6cacb3272645449d3063d9e11720b92adff6fac0dd4739e",25);
                denied(c,"ELMOS_OBJECT_GC_HOST_RECEIPT_INVALID",
                        "SELECT elmos_object_gc_host_confirm(?,?,?,?,?,?,?,?,?)",
                        item.runId(),item.contentObjectId(),org,item.contentSha256(),
                        item.backendId(),item.storageKey(),"request",
                        String.format("%064x",9),25);
                assertEquals("true",confirm(c,item));assertEquals("true",confirm(c,item));
                assertEquals("false",scalar(c,"SELECT elmos_object_gc_host_unknown(?,?)",item.runId(),item.contentObjectId()));
                assertEquals("CONFIRMED:1",scalar(c,"SELECT item_state||':'||unknown_count FROM object_gc_host_items WHERE run_id=?",item.runId()));
                assertEquals("COMPLETED:1",scalar(c,"SELECT run_state||':'||purged_count FROM object_gc_runs WHERE gc_run_id=?",item.runId()));
            } finally {c.rollback();}
        }
    }

    @Test void legacyUploadsNeverBecomePhysicalReclaimCandidates() throws Exception {
        try(Connection c=data.getConnection()) {
            c.setAutoCommit(false);
            try {
                String prefix=prefix(),org=prefix+"a";
                tenant(c,org);
                objects(c,org,1);
                execute(c,"""
                    INSERT INTO content_objects(
                        content_object_id,organization_id,content_sha256,byte_size,
                        backend_id,storage_key,upload_protocol,object_state,
                        uploaded_at,verified_at)
                    VALUES (?,?,repeat('f',64),100,'primary',?,
                            'LEGACY_UNFENCED','AVAILABLE',now(),now())
                    """,org+"-legacy",org,org+"/obj/legacy");
                scalar(c,"SELECT set_config('app.organization_id',?,true)",org);
                scalar(c,"SELECT elmos_expire_artifacts(?,100)",prefix+"expire");
                assertEquals("PURGE_PENDING",state(c,org+"-o1"));
                assertEquals("AVAILABLE",state(c,org+"-legacy"),
                        "backend reconfiguration cannot promote an unfenced upload");
                denied(c,"content_objects_purge_pending_requires_fence",
                        "UPDATE content_objects SET object_state='PURGE_PENDING' "
                                + "WHERE content_object_id=?",org+"-legacy");
            } finally {c.rollback();}
        }
    }

    @Test void retryCursorDoesNotLetFirstUnknownItemStarveLaterItems() throws Exception {
        try(Connection c=data.getConnection()) {
            c.setAutoCommit(false);
            try {
                String prefix=prefix(),org=prefix+"a";tenant(c,org);objects(c,org,3);cursor(c,prefix);
                assertEquals(3,prepare(c,1,3,3).size());
                cursor(c,prefix);var first=prepare(c,1,1,1).getFirst();
                scalar(c,"SELECT elmos_object_gc_host_unknown(?,?)",first.runId(),first.contentObjectId());
                cursor(c,prefix);var next=prepare(c,1,1,1).getFirst();
                assertNotEquals(first.contentObjectId(),next.contentObjectId());
                assertEquals(first.runId(),next.runId());
            } finally {c.rollback();}
        }
    }

    @Test void unknownAdmissionIsGlobalBoundedAndNeverEvictsAnOldRun() throws Exception {
        try(Connection c=data.getConnection()) {
            c.setAutoCommit(false);
            try {
                String prefix=prefix(),org=prefix+"z";tenant(c,org);objects(c,org,1);
                execute(c,"INSERT INTO organizations(organization_id) SELECT ?||n FROM generate_series(1,256) n",prefix);
                execute(c,"INSERT INTO object_gc_host_runs(run_id,organization_id,run_state,created_at) SELECT ?||n,?||n,'UNRESOLVED',now()-interval '100 years' FROM generate_series(1,256) n",prefix,prefix);
                cursor(c,org.substring(0,org.length()-1)+"y");
                assertTrue(prepare(c,1,1,1).isEmpty());
                assertEquals("AVAILABLE",state(c,org+"-o1"));
                assertEquals("256",scalar(c,"SELECT count(*) FROM object_gc_host_runs WHERE organization_id LIKE ? AND run_state='UNRESOLVED'",prefix+"%"));
                assertEquals(org,scalar(c,"SELECT last_organization_id FROM object_gc_host_cursor"),"full admission must not freeze tenant rotation");
            } finally {c.rollback();}
        }
    }

    @Test void onlyCompletedPrivateHistoryIsPrunedAndCleanupIsBounded() throws Exception {
        try(Connection c=data.getConnection()) {
            c.setAutoCommit(false);
            try {
                String prefix=prefix(),org=prefix+"a";tenant(c,org);cursor(c,prefix);
                execute(c,"INSERT INTO object_gc_host_runs(run_id,organization_id,run_state,finished_at) SELECT ?||n,?,'COMPLETED',now() FROM generate_series(1,4000) n",prefix,org);
                long before=Long.parseLong(scalar(c,"SELECT count(*) FROM object_gc_host_runs"));
                prepare(c,1,1,1);
                long after=Long.parseLong(scalar(c,"SELECT count(*) FROM object_gc_host_runs"));
                assertEquals(before-32+1,after,"at most 32 terminal ledgers cleaned; one empty run completed");
            } finally {c.rollback();}
        }
    }

    @Test void rollbackDoesNotPublishDeletionAuthority() throws Exception {
        String prefix=prefix(),org=prefix+"a";
        try(Connection c=data.getConnection()) {
            tenant(c,org);objects(c,org,1);
            c.setAutoCommit(false);
            try {cursor(c,prefix);assertEquals(1,prepare(c,1,1,1).size());} finally {c.rollback();}
            assertEquals("AVAILABLE",state(c,org+"-o1"));
            assertEquals("0",scalar(c,"SELECT count(*) FROM object_gc_host_runs WHERE organization_id=?",org));
        }
    }

    @Test void preparedWriterObjectLockCannotBeTurnedIntoDeletionAuthority() throws Exception {
        String prefix=prefix(),org=prefix+"a";
        try(Connection c=data.getConnection()){tenant(c,org);objects(c,org,1);cursor(c,prefix);}
        try(Connection writer=data.getConnection();Connection collector=data.getConnection()) {
            writer.setAutoCommit(false);collector.setAutoCommit(false);
            try {
                scalar(writer,"SELECT set_config('app.organization_id',?,true)",org);
                scalar(writer,"SELECT content_object_id FROM content_objects WHERE content_object_id=? FOR UPDATE",org+"-o1");
                assertTrue(prepare(collector,1,1,1).isEmpty(),"GC must SKIP the writer's actual object lock");
                collector.rollback();
                scalar(writer,"SELECT elmos_prepare_execution_input(?,?,?,?,?,CAST(100 AS bigint))",
                        prefix+"input",org,"writer",org+"-o1",String.format("%064x",1));
                writer.commit();
                cursor(collector,prefix);
                assertTrue(prepare(collector,1,1,1).isEmpty(),"new snapshot must see the committed PREPARED root");
                assertEquals("AVAILABLE",state(collector,org+"-o1"));
            } finally {writer.rollback();collector.rollback();}
        }
    }

    @Test void blockedProviderCallbackHasNoJdbcConnectionAndUnknownRemainsPending() throws Exception {
        String prefix=prefix(),org=prefix+"a";
        try(Connection c=data.getConnection()){tenant(c,org);objects(c,org,1);cursor(c,prefix);}
        TrackingDataSource tracking=new TrackingDataSource(data);
        var transactions=new TransactionTemplate(new DataSourceTransactionManager(tracking));
        var store=new JdbcTenantObjectRetentionStore(JdbcClient.create(tracking),transactions);
        AtomicInteger callbacks=new AtomicInteger();
        transactions.executeWithoutResult(status -> assertThrows(IllegalStateException.class,
                ()->store.collect(purge->{callbacks.incrementAndGet();return receipt();})));
        assertEquals(0,callbacks.get());
        CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);
        try(var pool=Executors.newSingleThreadExecutor()) {
            var future=pool.submit(()->store.collect(purge->{
                assertEquals(0,tracking.open.get(),"metadata connection must be returned before any provider callback");
                if(purge.organizationId().equals(org)) {
                    entered.countDown();
                    try {assertTrue(release.await(30,TimeUnit.SECONDS));} catch(InterruptedException e){throw new RuntimeException(e);}
                }
                throw new IllegalStateException("controlled unknown provider result");
            }));
            try {
                assertTrue(entered.await(60,TimeUnit.SECONDS));assertEquals(0,tracking.open.get());
                try(Connection c=data.getConnection()){assertEquals("PURGE_PENDING",state(c,org+"-o1"));}
            } finally {release.countDown();}
            var result=future.get(60,TimeUnit.SECONDS);assertEquals(0,result.confirmed());assertTrue(result.unknown()>=1);
        }
        try(Connection c=data.getConnection()) {
            assertEquals("UNKNOWN",scalar(c,"SELECT item_state FROM object_gc_host_items WHERE organization_id=?",org));
            cursor(c,prefix);
        }
        var confirmed=store.collect(purge->{
            assertEquals(0,tracking.open.get());return receipt();});
        assertTrue(confirmed.confirmed()>=1);
        try(Connection c=data.getConnection()){assertEquals("PURGED",state(c,org+"-o1"));}
    }

    static final class TrackingDataSource extends DelegatingDataSource {
        final AtomicInteger open=new AtomicInteger();
        TrackingDataSource(DriverManagerDataSource delegate){super(delegate);}
        @Override public Connection getConnection() throws SQLException {
            Connection connection=super.getConnection();
            execute(connection,"SET ROLE elmos_object_gc_host");open.incrementAndGet();
            return (Connection)Proxy.newProxyInstance(Connection.class.getClassLoader(),new Class<?>[]{Connection.class},(proxy,method,args)->{
                try {return method.invoke(connection,args);} catch(InvocationTargetException e){throw e.getCause();}
                finally {if(method.getName().equals("close"))open.decrementAndGet();}
            });
        }
    }
    static String prefix(){return "gch-"+UUID.randomUUID()+"-";}
    static void tenant(Connection c,String org) throws SQLException {execute(c,"INSERT INTO organizations(organization_id) VALUES(?)",org);}
    static void objects(Connection c,String org,int count) throws SQLException {
        execute(c,"""
            INSERT INTO content_objects(content_object_id,organization_id,content_sha256,byte_size,backend_id,storage_key,upload_protocol,object_state,uploaded_at,verified_at)
            SELECT ?||'-o'||n,?,lpad(to_hex(n),64,'0'),100,'primary',?||'/obj/'||lpad(to_hex(n),64,'0'),'WRITE_ONCE_RECLAIM_FENCE_V1','AVAILABLE',now(),now()
            FROM generate_series(1,?) n
            """,org,org,org,count);
    }
    static S3ObjectStore.ReclaimReceipt receipt() {
        return new S3ObjectStore.ReclaimReceipt(
                "provider-request-fixture",
                "d835c506a9a8f23ea6cacb3272645449d3063d9e11720b92adff6fac0dd4739e",
                25);
    }
    static void artifacts(Connection c,String org,int count) throws SQLException {
        execute(c,"""
            INSERT INTO execution_jobs(job_id,organization_id,actor_id,business_line,job_kind,idempotency_key,request_digest,required_capability,request_payload)
            VALUES (?,?,'fixture','TRANSLATION','translate-analyze-v1',?,repeat('a',64),'translation:multi','{}')
            """,org+"-job",org,org+"-job");
        execute(c,"""
            INSERT INTO job_artifacts(artifact_id,organization_id,job_id,artifact_role,filename,content_object_ref,expires_at)
            SELECT ?||'-a'||n,?,?,'BUILD_LOG',n::text,?||'-o'||n,now()-interval '1 day' FROM generate_series(1,?) n
            """,org,org,org+"-job",org,count);
    }
    static void cursor(Connection c,String prefix) throws SQLException {execute(c,"UPDATE object_gc_host_cursor SET last_organization_id=?",prefix);}
    static String state(Connection c,String object) throws SQLException {return scalar(c,"SELECT object_state FROM content_objects WHERE content_object_id=?",object);}
    static List<JdbcTenantObjectRetentionStore.Purge> prepare(Connection c,int tenants,int metadata,int deletes) throws SQLException {
        try(var p=c.prepareStatement("SELECT * FROM elmos_object_gc_host_prepare(?,?,?,?)")) {
            p.setString(1,UUID.randomUUID().toString());p.setInt(2,tenants);p.setInt(3,metadata);p.setInt(4,deletes);
            List<JdbcTenantObjectRetentionStore.Purge> result=new ArrayList<>();
            try(var r=p.executeQuery()){while(r.next())result.add(new JdbcTenantObjectRetentionStore.Purge(r.getString(1),r.getString(2),r.getString(3),r.getString(4),r.getString(5),r.getString(6)));}
            return result;
        }
    }
    static String confirm(Connection c,JdbcTenantObjectRetentionStore.Purge p) throws SQLException {
        return scalar(c,"SELECT elmos_object_gc_host_confirm(?,?,?,?,?,?,?,?,?)",
                p.runId(),p.contentObjectId(),p.organizationId(),p.contentSha256(),
                p.backendId(),p.storageKey(),"provider-request-fixture",
                "d835c506a9a8f23ea6cacb3272645449d3063d9e11720b92adff6fac0dd4739e",25);
    }
    static void denied(Connection c,String code,String sql,Object...args) throws SQLException {
        var savepoint=c.setSavepoint();
        try {SQLException e=assertThrows(SQLException.class,()->scalar(c,sql,args));assertTrue(e.getMessage().contains(code),e.getMessage());}
        finally {c.rollback(savepoint);}
    }
    static void execute(Connection c,String sql,Object...args) throws SQLException {try(var p=c.prepareStatement(sql)){for(int i=0;i<args.length;i++)p.setObject(i+1,args[i]);p.execute();}}
    static String scalar(Connection c,String sql,Object...args) throws SQLException {try(var p=c.prepareStatement(sql)){for(int i=0;i<args.length;i++)p.setObject(i+1,args[i]);try(var r=p.executeQuery()){assertTrue(r.next());return String.valueOf(r.getObject(1));}}}
}
