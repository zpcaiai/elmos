package io.elmos.workflow;

import io.elmos.application.WorkflowStatePort;
import io.elmos.domain.*;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class DurableWorkflowServiceTest {
    @Test void rejectsSkippedStateAndUsesOptimisticVersion() {
        var id=MigrationRunId.random();
        class Fake implements WorkflowStatePort {
            Snapshot value=new Snapshot(id,MigrationState.CREATED,0);
            public Snapshot load(MigrationRunId ignored){return value;}
            public Snapshot compareAndSet(MigrationRunId ignored,long expected,MigrationState from,MigrationState to,String event){
                if(value.version()!=expected||value.state()!=from)throw new DomainException("optimistic lock conflict");
                return value=new Snapshot(id,to,expected+1);
            }
        }
        var fake=new Fake(); var service=new DurableWorkflowService(fake);
        assertThrows(DomainException.class,()->service.transition(id,MigrationState.MIGRATING,"skip"));
        assertEquals(1,service.transition(id,MigrationState.REPOSITORY_PREPARING,"start").version());
    }
}

