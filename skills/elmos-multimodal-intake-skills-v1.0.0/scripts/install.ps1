param(
    [Parameter(Mandatory=$true)]
    [string]$Target,

    [ValidateSet("Both", "Codex", "Claude")]
    [string]$Mode = "Both",

    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageRoot = Resolve-Path (Join-Path $ScriptDir "..")
$Source = Join-Path $PackageRoot "skills"

if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
    throw "Target repository does not exist: $Target"
}
if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    throw "Canonical skills directory not found: $Source"
}

function Copy-SkillSet {
    param([string]$Destination)

    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    }

    $copied = 0
    $skipped = 0
    $items = Get-ChildItem -LiteralPath $Source -Directory | Sort-Object Name
    foreach ($item in $items) {
        $targetDir = Join-Path $Destination $item.Name
        if ((Test-Path -LiteralPath $targetDir) -and -not $Force) {
            Write-Host "SKIP existing: $targetDir"
            $skipped++
            continue
        }

        Write-Host "INSTALL: $($item.FullName) -> $targetDir"
        if (-not $DryRun) {
            if (Test-Path -LiteralPath $targetDir) {
                Remove-Item -LiteralPath $targetDir -Recurse -Force
            }
            Copy-Item -LiteralPath $item.FullName -Destination $targetDir -Recurse
        }
        $copied++
    }
    Write-Host "Result for ${Destination}: copied=$copied skipped=$skipped"
}

switch ($Mode) {
    "Codex"  { Copy-SkillSet (Join-Path $Target ".agents/skills") }
    "Claude" { Copy-SkillSet (Join-Path $Target ".claude/skills") }
    "Both" {
        Copy-SkillSet (Join-Path $Target ".agents/skills")
        Copy-SkillSet (Join-Path $Target ".claude/skills")
    }
}

Write-Host "Installation complete. Canonical source remains: $Source"
