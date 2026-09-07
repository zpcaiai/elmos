$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& python "$RootDir/scripts/verify_package.py" --root "$RootDir" @args
exit $LASTEXITCODE
