package io.elmos.persistence;

import io.elmos.application.WorkflowStatePort;
import io.elmos.domain.DomainException;
import io.elmos.domain.MigrationRunId;
import io.elmos.domain.MigrationState;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Repository
public class JdbcWorkflowStateAdapter implements WorkflowStatePort {
    private final JdbcTemplate jdbc;
    public JdbcWorkflowStateAdapter(JdbcTemplate jdbc){this.jdbc=jdbc;}
    @Override public Snapshot load(MigrationRunId id){return jdbc.queryForObject("select state,version from migration_runs where migration_run_id=?",(rs,n)->new Snapshot(id,MigrationState.valueOf(rs.getString(1)),rs.getLong(2)),id.value());}
    @Override @Transactional public Snapshot compareAndSet(MigrationRunId id,long version,MigrationState from,MigrationState to,String eventType){
        int changed=jdbc.update("update migration_runs set state=?,version=version+1 where migration_run_id=? and state=? and version=?",to.name(),id.value(),from.name(),version);
        if(changed!=1)throw new DomainException("optimistic lock conflict for "+id.value());
        jdbc.update("insert into outbox_events(event_id,aggregate_type,aggregate_id,event_type,occurred_at,attributes) values (?,?,?,?,?,?)",UUID.randomUUID().toString(),"MIGRATION_RUN",id.value(),eventType,Instant.now(),"{state="+to.name()+"}");
        return new Snapshot(id,to,version+1);
    }
}

