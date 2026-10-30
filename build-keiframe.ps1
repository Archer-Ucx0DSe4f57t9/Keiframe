[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# One canonical release pipeline: keep the main package and OCR addon separate.
$scriptPath = Join-Path $PSScriptRoot "build-keiframe.bat"
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Build script was not found: $scriptPath"
}
& $scriptPath
if ($LASTEXITCODE -ne 0) {
    throw "Keiframe release build failed with exit code $LASTEXITCODE."
}
