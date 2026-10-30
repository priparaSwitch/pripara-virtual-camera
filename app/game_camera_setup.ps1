# Source-tree convenience entry point. The packaged application receives the
# complete installer/GameCameraSetup.ps1 beside its executable instead.
& (Join-Path (Split-Path $PSScriptRoot -Parent) 'installer\GameCameraSetup.ps1') @args
exit $LASTEXITCODE
