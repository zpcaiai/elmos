$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& python "$RootDir/scripts/manage_install.py" install @args
exit $LASTEXITCODE
