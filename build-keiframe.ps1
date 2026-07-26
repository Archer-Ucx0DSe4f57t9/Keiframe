[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$specPath = Join-Path $projectDirectory "Keiframe.spec"
$outputDirectory = Join-Path $projectDirectory "dist\Keiframe"

$pythonCandidates = @(
    (Join-Path $projectDirectory ".venv\Scripts\python.exe"),
    (Join-Path $projectDirectory "python\python.exe")
)
$pythonPath = $pythonCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1

if (-not $pythonPath) {
    throw "Python runtime was not found. Create .venv and install requirements.txt."
}
if (-not (Test-Path -LiteralPath $specPath -PathType Leaf)) {
    throw "PyInstaller spec was not found: $specPath"
}

& $pythonPath -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed in: $pythonPath"
}

Write-Host "Python: $pythonPath"
Write-Host "Building Keiframe.exe..."
Push-Location $projectDirectory
try {
    & $pythonPath -m PyInstaller --clean --noconfirm $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $resourcesPath = Join-Path $projectDirectory "resources"
    if (Test-Path -LiteralPath $resourcesPath -PathType Container) {
        Copy-Item `
            -LiteralPath $resourcesPath `
            -Destination $outputDirectory `
            -Recurse `
            -Force
    }

    foreach ($fileName in @("README.zh-CN.md")) {
        $sourcePath = Join-Path $projectDirectory $fileName
        if (Test-Path -LiteralPath $sourcePath -PathType Leaf) {
            Copy-Item `
                -LiteralPath $sourcePath `
                -Destination $outputDirectory `
                -Force
        }
    }
}
finally {
    Pop-Location
}

$executablePath = Join-Path $outputDirectory "Keiframe.exe"
$requiredResource = Join-Path $outputDirectory "resources\db\maps.db"
if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw "Expected executable was not generated: $executablePath"
}
if (-not (Test-Path -LiteralPath $requiredResource -PathType Leaf)) {
    throw "Runtime resources were not copied: $requiredResource"
}

Write-Host ""
Write-Host "Keiframe package build complete:"
Write-Host "  $executablePath"
