package io.elmos.architecture;

import com.tngtech.archunit.core.importer.ClassFileImporter;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

class ArchitectureRulesTest {
    private final com.tngtech.archunit.core.domain.JavaClasses classes = new ClassFileImporter().importPackages("io.elmos");

    @Test void domainHasNoFrameworkOrInfrastructureDependencies(){
        noClasses().that().resideInAPackage("io.elmos.domain..").should().dependOnClassesThat().resideInAnyPackage("org.springframework..","jakarta.persistence..","io.elmos.persistence..","io.elmos.integrations..").check(classes);
    }
    @Test void applicationUsesPortsInsteadOfAdapters(){
        noClasses().that().resideInAPackage("io.elmos.application..").should().dependOnClassesThat().resideInAnyPackage("io.elmos.persistence..","io.elmos.integrations..").check(classes);
    }
    @Test void controlPlaneCannotExecuteCustomerCommands(){
        noClasses().that().resideInAPackage("io.elmos.controlplane..").should().dependOnClassesThat().resideInAnyPackage("com.github.dockerjava..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void workerCannotAccessControlPlaneDatabase(){
        noClasses().that().resideInAPackage("io.elmos.worker..").should().dependOnClassesThat().resideInAnyPackage("java.sql..","org.springframework.jdbc..","io.elmos.persistence..").check(classes);
    }
    @Test void workspaceCoreHasNoDockerOrSpringDependency(){
        noClasses().that().resideInAPackage("io.elmos.workspace..").should().dependOnClassesThat()
                .resideInAnyPackage("com.github.dockerjava..", "org.springframework..").check(classes);
    }
    @Test void workspaceServiceUsesDockerApiNotHostProcesses(){
        noClasses().that().resideInAPackage("io.elmos.workspaceservice..").should().dependOnClassesThat()
                .haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void pureCoreModulesRemainFrameworkAndStorageFree(){
        noClasses().that().resideInAnyPackage("io.elmos.health..", "io.elmos.intake..", "io.elmos.skeleton..", "io.elmos.lowering..", "io.elmos.dependency..", "io.elmos.frameworkmigration..", "io.elmos.composite..", "io.elmos.planning..", "io.elmos.recipe..", "io.elmos.repair..", "io.elmos.validation..", "io.elmos.delivery..", "io.elmos.enterprise..", "io.elmos.commercial..", "io.elmos.roadmap..", "io.elmos.migrationpack..").should().dependOnClassesThat()
                .resideInAnyPackage("org.springframework..", "java.sql..", "com.github.dockerjava..", "io.elmos.persistence..").check(classes);
    }
    @Test void evidenceBoundDomainCoreRemainsFrameworkStorageAndExecutorFree(){
        noClasses().that().resideInAPackage("io.elmos.executiondomain..").should().dependOnClassesThat()
                .resideInAnyPackage("org.springframework..", "java.sql..", "org.springframework.jdbc..",
                        "com.github.dockerjava..", "io.elmos.persistence..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void batchTwentyTwoThroughTwentySixWorkersCannotReadControlPersistenceOrRunHostProcesses(){
        noClasses().that().resideInAnyPackage("io.elmos.deliveryplatform..", "io.elmos.ai..", "io.elmos.industrial..",
                        "io.elmos.operations..", "io.elmos.ea..").should().dependOnClassesThat()
                .resideInAnyPackage("java.sql..", "org.springframework.jdbc..", "io.elmos.persistence..",
                        "com.github.dockerjava..", "io.elmos.controlplane..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void compositeOrchestratorCannotBecomeALanguageTransformer(){
        noClasses().that().resideInAPackage("io.elmos.composite..").should().dependOnClassesThat()
                .resideInAnyPackage("org.openrewrite..", "io.elmos.worker..", "io.elmos.frameworkmigration..",
                        "io.elmos.recipe..", "io.elmos.repair..", "io.elmos.agentgateway..").check(classes);
    }
    @Test void semanticCoreOnlyUsesLocalArtifactStorage(){
        noClasses().that().resideInAnyPackage("io.elmos.semantic..", "io.elmos.uir..").should().dependOnClassesThat()
                .resideInAnyPackage("org.springframework..", "com.github.dockerjava..", "io.elmos.persistence..").check(classes);
    }
    @Test void egressProxyCannotUseDatabaseOrHostProcesses(){
        noClasses().that().resideInAPackage("io.elmos.egressproxy..").should().dependOnClassesThat()
                .resideInAnyPackage("java.sql..", "org.springframework.jdbc..", "io.elmos.persistence..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void qualityJudgeIsIndependentFromTransformationAndRepair(){
        noClasses().that().resideInAPackage("io.elmos.validation..").should().dependOnClassesThat()
                .resideInAnyPackage("io.elmos.recipe..", "io.elmos.repair..", "io.elmos.worker..", "io.elmos.agentgateway..").check(classes);
    }
    @Test void agentGatewayCannotUseDatabaseDockerOrHostProcesses(){
        noClasses().that().resideInAPackage("io.elmos.agentgateway..").should().dependOnClassesThat()
                .resideInAnyPackage("java.sql..", "org.springframework.jdbc..", "io.elmos.persistence..", "com.github.dockerjava..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void databaseDataWorkerCannotUseControlPlanePersistenceOrHostProcesses(){
        noClasses().that().resideInAPackage("io.elmos.databasedata..").should().dependOnClassesThat()
                .resideInAnyPackage("java.sql..", "org.springframework.jdbc..", "io.elmos.persistence..",
                        "com.github.dockerjava..", "io.elmos.controlplane..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void enterpriseIntegrationWorkerCannotUseControlPlanePersistenceOrHostProcesses(){
        noClasses().that().resideInAPackage("io.elmos.integration..").should().dependOnClassesThat()
                .resideInAnyPackage("java.sql..", "org.springframework.jdbc..", "io.elmos.persistence..",
                        "com.github.dockerjava..", "io.elmos.controlplane..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void enterpriseSuiteWorkerCannotUseControlPlanePersistenceDockerOrHostProcesses(){
        noClasses().that().resideInAPackage("io.elmos.suite..").should().dependOnClassesThat()
                .resideInAnyPackage("java.sql..", "org.springframework.jdbc..", "io.elmos.persistence..",
                        "com.github.dockerjava..", "io.elmos.controlplane..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void enterpriseControlCannotExecuteCustomerWorkOrReadPersistenceDirectly(){
        noClasses().that().resideInAPackage("io.elmos.enterprisecontrol..").should().dependOnClassesThat()
                .resideInAnyPackage("java.sql..", "org.springframework.jdbc..", "io.elmos.persistence..", "com.github.dockerjava..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void commercialApiCannotBecomePaymentAccountingOrCustomerExecutor(){
        noClasses().that().resideInAPackage("io.elmos.commercialapi..").should().dependOnClassesThat()
                .resideInAnyPackage("java.sql..", "org.springframework.jdbc..", "io.elmos.persistence..", "com.github.dockerjava..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
    @Test void elmosCtlCannotDirectlyRunHostCommandsOrReadPersistence(){
        noClasses().that().resideInAPackage("io.elmos.cli..").should().dependOnClassesThat()
                .resideInAnyPackage("java.sql..", "io.elmos.persistence..", "com.github.dockerjava..")
                .orShould().dependOnClassesThat().haveFullyQualifiedName("java.lang.ProcessBuilder").check(classes);
    }
}
