namespace Elmos.Dotnet.Wcf;

public sealed record WcfMigrationDecision(string Target, string Automation, bool ArchitectureApproval, IReadOnlyList<string> Gates);

public sealed class WcfMigrationAdvisor
{
    public WcfMigrationDecision Decide(string binding, bool existingSoapClients, bool transactionFlow, bool duplex)
    {
        var normalized = binding.ToUpperInvariant();
        if (normalized.Contains("CUSTOM")) return new("ARCHITECTURE_DECISION", "PARTIAL", true, ["WSDL", "SOAP", "SECURITY", "TRANSACTION", "CUSTOM_BINDING_BEHAVIOR"]);
        if (normalized.Contains("NETTCP") || existingSoapClients) return new("COREWCF_CANDIDATE", "ASSISTED", transactionFlow || duplex, ["WSDL", "SOAP", "CLIENT_REGRESSION", "SECURITY", "TRANSACTION"]);
        return new("COREWCF_OR_GRPC_OR_REST_DECISION", "ASSISTED", true, ["CONTRACT", "CLIENT_REGRESSION", "SECURITY"]);
    }
}
