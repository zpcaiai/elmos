# Read-only machine discovery plus a disposable native file-lock probe.
# Does not enable Hyper-V, switch Docker mode, install software or change policy.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$result = [ordered]@{ schema = 'elmos.windows-host-observation.v1'; evidence = 'LOCAL_EXECUTED_SELF_ATTESTED' }
$result.powershell = $PSVersionTable.PSVersion.ToString()
$result.culture = [System.Globalization.CultureInfo]::CurrentCulture.Name
$result.uiCulture = [System.Globalization.CultureInfo]::CurrentUICulture.Name
$result.processArchitecture = $env:PROCESSOR_ARCHITECTURE
try {
    $os = Get-CimInstance Win32_OperatingSystem -OperationTimeoutSec 5
    $result.os = @{ caption = $os.Caption; version = $os.Version; build = $os.BuildNumber; architecture = $os.OSArchitecture }
    $computer = Get-CimInstance Win32_ComputerSystem -OperationTimeoutSec 5
    $result.machine = @{ manufacturer = $computer.Manufacturer; model = $computer.Model; hypervisorPresent = $computer.HypervisorPresent; domainJoined = $computer.PartOfDomain }
} catch { $result.cim = 'UNKNOWN' }
try { $result.systemLocale = (Get-WinSystemLocale).Name } catch { $result.systemLocale = 'UNKNOWN' }
try { $result.longPathsEnabled = (Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem').LongPathsEnabled } catch { $result.longPathsEnabled = 'UNKNOWN' }
$result.features = 'NOT_RUN_REQUIRES_SEPARATE_PRIVILEGED_DISCOVERY'
try { $result.hypervService = (Get-Service -Name vmms -ErrorAction Stop).Status.ToString() } catch { $result.hypervService = 'UNKNOWN_OR_NOT_INSTALLED' }
try { $result.volumes = @([System.IO.DriveInfo]::GetDrives() | Where-Object { $_.IsReady -and $_.DriveType -eq 'Fixed' } | Select-Object Name, DriveFormat) } catch { $result.volumes = 'UNKNOWN' }
$result.odbcDrivers = @{}
foreach ($registryPath in @('HKLM:\SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers', 'HKLM:\SOFTWARE\WOW6432Node\ODBC\ODBCINST.INI\ODBC Drivers')) {
    try { $result.odbcDrivers[$registryPath] = @((Get-Item -LiteralPath $registryPath).GetValueNames()) } catch { $result.odbcDrivers[$registryPath] = @() }
}
# Do not export domain names, certificate subjects, proxy credentials or DSN connection strings.
$result.tools = @{}
foreach ($name in @('cmd.exe', 'java.exe', 'mvn.cmd', 'dotnet.exe', 'MSBuild.exe', 'sqlcmd.exe')) {
    $tool = Get-Command $name -ErrorAction SilentlyContinue
    $result.tools[$name] = if ($tool) { $tool.Source } else { 'NOT_FOUND' }
}
$result.edge = 'NOT_FOUND'
foreach ($candidate in @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe")) {
    if (Test-Path -LiteralPath $candidate) { $result.edge = (Get-Item -LiteralPath $candidate).VersionInfo.ProductVersion; break }
}
$result.nativeFileLock = 'NOT_RUN'
$probePath = Join-Path ([System.IO.Path]::GetTempPath()) ('elmos-lock-' + [guid]::NewGuid().ToString('N'))
$stream = $null
try {
    $stream = [System.IO.File]::Open($probePath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    try {
        $second = [System.IO.File]::Open($probePath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $second.Dispose()
        $result.nativeFileLock = 'FAIL'
    } catch [System.IO.IOException] { $result.nativeFileLock = 'PASS' }
} finally {
    if ($null -ne $stream) { $stream.Dispose() }
    if (Test-Path -LiteralPath $probePath) { Remove-Item -LiteralPath $probePath }
    $result.lockProbeCleaned = -not (Test-Path -LiteralPath $probePath)
}
$result.certification = 'NOT_CERTIFIED'
$result | ConvertTo-Json -Depth 6 -Compress
