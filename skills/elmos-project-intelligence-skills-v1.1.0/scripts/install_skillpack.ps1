param(
  [Parameter(Mandatory=$true)][string]$Repo,
  [ValidateSet("codex","claude","both")][string]$Target = "both",
  [string]$Profile = "full",
  [switch]$Force,
  [switch]$NoShared,
  [switch]$DryRun
)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ArgsList = @("$ScriptDir/install_skillpack.py", "--repo", $Repo, "--target", $Target, "--profile", $Profile)
if ($Force) { $ArgsList += "--force" }
if ($NoShared) { $ArgsList += "--no-shared" }
if ($DryRun) { $ArgsList += "--dry-run" }
python @ArgsList
exit $LASTEXITCODE
