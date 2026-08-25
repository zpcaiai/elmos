using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Elmos.Dotnet.Domain;

namespace Elmos.Dotnet.Infrastructure;

public sealed class UnifiedEvidenceMapper
{
    public UnifiedEvidenceExtension Map(string organizationId, string snapshotRef, string artifactType, object artifact, EvidenceStatus status)
    {
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
        options.Converters.Add(new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseUpper));
        var json = JsonSerializer.Serialize(artifact, options);
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(json))).ToLowerInvariant();
        return new("1.0", organizationId, snapshotRef, "ELMOS_DOTNET", "1.0.0", artifactType, hash, status,
            new Dictionary<string, object?> { ["artifact"] = artifact, ["provider"] = "ELMOS_DOTNET", ["providerVersion"] = "1.0.0" });
    }
}
