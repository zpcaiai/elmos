namespace Elmos.Dotnet.AspNet;

public sealed record AspNetMigrationDecision(string Strategy, bool UiRewriteRequired, bool UseYarp, bool UseSystemWebAdapters, IReadOnlyList<string> Gates, IReadOnlyList<string> ExitDecisions);

public sealed class AspNetMigrationAdvisor
{
    public AspNetMigrationDecision Decide(bool webForms, bool systemWebSharedLibraries, bool productionMustStayOnline)
    {
        if (webForms || productionMustStayOnline)
            return new("INCREMENTAL_SIDE_BY_SIDE", webForms, true, systemWebSharedLibraries, ["HTTP_CONTRACT", "SESSION", "AUTH", "CACHE", "ROUTING"], systemWebSharedLibraries ? ["REMOVE_SYSTEM_WEB_ADAPTERS", "APPROVE_LONG_TERM_ADAPTER"] : ["REMOVE_YARP_AFTER_ROUTE_CUTOVER"]);
        return new("IN_PLACE_ASPNET_CORE", false, false, false, ["HTTP_CONTRACT", "AUTH", "SERIALIZATION"], []);
    }
}
