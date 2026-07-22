namespace Elmos.Dotnet.Ef;

public sealed record EfContextStep(string Context, string Strategy, IReadOnlyList<string> Gates);
public sealed record EfMigrationPlan(IReadOnlyList<string> RuntimeSteps, IReadOnlyList<EfContextStep> ContextSteps, bool RebuildMigrationBaseline, bool RegenerateEdmxModel);

public sealed class EfMigrationPlanner
{
    public EfMigrationPlan Plan(IReadOnlyList<string> contexts, bool hasEdmx) => new(
        ["MOVE_APPLICATION_TO_MODERN_DOTNET_WHILE_KEEPING_EF6", "VALIDATE_EF6_ON_MODERN_RUNTIME"],
        contexts.Select(context => new EfContextStep(context, hasEdmx ? "SCAFFOLD_CANDIDATE_FROM_TEST_DATABASE" : "PORT_CONTEXT_TO_EF_CORE", ["SCHEMA", "SQL", "QUERY_RESULT", "TRANSACTION", "CONCURRENCY"])).ToArray(),
        true,
        hasEdmx);
}
