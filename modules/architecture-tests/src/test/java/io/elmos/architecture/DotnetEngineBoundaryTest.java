package io.elmos.architecture;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class DotnetEngineBoundaryTest {
    private final Path root=Path.of(System.getProperty("basedir")).resolve("../..").normalize();

    @Test void javaControlPlaneDoesNotLoadRoslynOrMsBuild() throws Exception {
        String pom=Files.readString(root.resolve("apps/control-plane/pom.xml"));
        assertFalse(pom.contains("CodeAnalysis"));
        assertFalse(pom.contains("MSBuild"));
        assertFalse(pom.contains("Elmos.Dotnet"));
    }

    @Test void dotnetWorkerHasNoControlPlaneDatabaseScmBillingOrSecretAdapter() throws Exception {
        Path engine=root.resolve("engines/dotnet-engine");
        String all=Files.walk(engine.resolve("src")).filter(Files::isRegularFile).filter(path->path.toString().endsWith(".cs")||path.toString().endsWith(".csproj"))
                .map(path->{try{return Files.readString(path);}catch(Exception error){throw new IllegalStateException(error);}}).reduce("",String::concat);
        assertFalse(all.contains("Npgsql"));
        assertFalse(all.contains("EntityFrameworkCore"));
        assertFalse(all.contains("Octokit"));
        assertFalse(all.contains("Billing"));
        assertFalse(all.contains("ControlPlaneSecret"));
        String program=Files.readString(engine.resolve("src/Elmos.Dotnet.Worker/Program.cs"));
        assertTrue(program.contains("/engine/v1/scan"));
        assertTrue(program.contains("/engine/v1/plan"));
        assertTrue(program.contains("/engine/v1/execute-step"));
        assertTrue(program.contains("/engine/v1/validate"));
    }

    @Test void pythonEngineKeepsLibCstAndCustomerExecutionOutsideJavaControlPlane() throws Exception {
        String controlPlanePom=Files.readString(root.resolve("apps/control-plane/pom.xml"));
        assertFalse(controlPlanePom.toLowerCase().contains("libcst"));
        assertFalse(controlPlanePom.toLowerCase().contains("mypy"));
        assertFalse(controlPlanePom.toLowerCase().contains("pyright"));
        Path engine=root.resolve("engines/python-engine/src");
        String all=Files.walk(engine).filter(Files::isRegularFile).filter(path->path.toString().endsWith(".py"))
                .map(path->{try{return Files.readString(path);}catch(Exception error){throw new IllegalStateException(error);}}).reduce("",String::concat);
        assertFalse(all.contains("psycopg"));
        assertFalse(all.contains("sqlalchemy"));
        assertFalse(all.contains("Octokit"));
        assertFalse(all.contains("ControlPlaneSecret"));
        String worker=Files.readString(root.resolve("engines/python-engine/src/elmos_python/worker/main.py"));
        assertTrue(worker.contains("/engine/v1/scan"));
        assertTrue(worker.contains("/engine/v1/plan"));
        assertTrue(worker.contains("/engine/v1/execute-step"));
        assertTrue(worker.contains("/engine/v1/validate"));
    }
}
