using Elmos.Dotnet.Application;
using Elmos.Dotnet.Domain;

namespace Elmos.Dotnet.Validation;

public sealed class DotnetValidationJudge : IValidationJudge
{
    public ValidationDecision Judge(ValidationInput input)
    {
        var observations = new List<ValidationObservation>
        {
            new("BASELINE_WINDOWS", input.BaselineWindowsPassed ? EvidenceStatus.Passed : EvidenceStatus.Failed, "evidence:baseline-windows", "Legacy Windows baseline is a separate environment."),
            new("MIGRATED_WINDOWS", input.MigratedWindowsPassed ? EvidenceStatus.Passed : EvidenceStatus.Failed, "evidence:migrated-windows", "Modern Windows result does not substitute for Linux."),
            new("TEST_INVENTORY", input.MigratedTests >= input.BaselineTests ? EvidenceStatus.Passed : EvidenceStatus.Failed, "evidence:test-inventory", $"baseline={input.BaselineTests}; migrated={input.MigratedTests}"),
            new("MIGRATED_LINUX", !input.LinuxRequired ? EvidenceStatus.NotRun : input.MigratedLinuxPassed ? EvidenceStatus.Passed : EvidenceStatus.Failed, "evidence:migrated-linux", input.LinuxRequired ? "Cross-platform target requires Linux evidence." : "Linux is not a target for this decision.")
        };
        observations.AddRange(input.ContractObservations);
        var blockers = observations.Where(o => o.Status is EvidenceStatus.Failed or EvidenceStatus.Blocked or EvidenceStatus.Inconclusive || (o.Gate == "MIGRATED_LINUX" && input.LinuxRequired && o.Status != EvidenceStatus.Passed)).Select(o => o.Gate).Distinct().ToArray();
        var status = blockers.Length > 0 ? EvidenceStatus.Failed : observations.Any(o => o.Status == EvidenceStatus.NotRun && o.Gate != "MIGRATED_LINUX") ? EvidenceStatus.Inconclusive : EvidenceStatus.Passed;
        return new(status, observations, blockers);
    }
}
