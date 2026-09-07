using Elmos.Dotnet.Application;
using Elmos.Dotnet.Contracts;
using Elmos.Dotnet.Infrastructure;
using System.Text.Json;
using System.Text.Json.Serialization;

var builder = WebApplication.CreateBuilder(args);
var approvedRoot = builder.Configuration["ELMOS_DOTNET_WORKSPACE_ROOT"] ?? Path.Combine(Path.GetTempPath(), "elmos-dotnet-workspaces");
builder.Services.AddSingleton<IDotnetEngine>(_ => new DotnetEngine(approvedRoot));
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase;
    options.SerializerOptions.Converters.Add(new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseUpper));
});
var app = builder.Build();

app.MapGet("/engine/v1/capabilities", (IDotnetEngine engine) => Results.Ok(engine.Capabilities()));
app.MapPost("/engine/v1/scan", (EngineJobRequest request, IDotnetEngine engine) => Accepted(engine.Scan(request)));
app.MapPost("/engine/v1/plan", (EngineJobRequest request, IDotnetEngine engine) => Accepted(engine.Plan(request)));
app.MapPost("/engine/v1/execute-step", (ExecuteStepRequest request, IDotnetEngine engine) => Accepted(engine.ExecuteStep(request)));
app.MapPost("/engine/v1/validate", (EngineJobRequest request, IDotnetEngine engine) => Accepted(engine.Validate(request)));
app.MapGet("/engine/v1/jobs/{jobId}", (string jobId, string organizationId, IDotnetEngine engine) => Visible(engine.GetJob(organizationId, jobId)));
app.MapPost("/engine/v1/jobs/{jobId}/cancel", (string jobId, string organizationId, IDotnetEngine engine) => Visible(engine.Cancel(organizationId, jobId)));
app.MapGet("/health", () => Results.Ok(new { status = "UP", engine = "ELMOS_DOTNET" }));

app.Run();

static IResult Accepted(EngineJobResponse response) => response.Error?.ErrorCode switch
{
    DotnetErrorCode.InvalidRequest => Results.BadRequest(response.Error),
    DotnetErrorCode.IdempotencyConflict => Results.Conflict(response.Error),
    _ => Results.Accepted($"/engine/v1/jobs/{response.JobId}", response)
};
static IResult Visible(EngineJobResponse response) => response.Error switch
{
    { ErrorCode: DotnetErrorCode.JobNotFound } => Results.NotFound(response.Error),
    { ErrorCode: DotnetErrorCode.JobTerminal } => Results.Conflict(response.Error),
    not null => Results.Conflict(response.Error),
    _ => Results.Ok(response)
};

public partial class Program;
