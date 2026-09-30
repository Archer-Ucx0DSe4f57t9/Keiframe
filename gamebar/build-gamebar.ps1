[CmdletBinding()]
param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Debug",

    [ValidateSet("x64")]
    [string]$Platform = "x64",

    [string]$OutputDirectory = "",

    [switch]$NoRestore
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectPath = Join-Path `
    $scriptDirectory `
    "Keiframe.GameBar\Keiframe.GameBar.csproj"

if (-not (Test-Path -LiteralPath $projectPath -PathType Leaf)) {
    throw "Game Bar project was not found: $projectPath"
}

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $scriptDirectory "artifacts\GameBar"
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$msbuildCandidates = @()
$msbuildCommand = Get-Command "MSBuild.exe" -ErrorAction SilentlyContinue
if ($msbuildCommand) {
    $msbuildCandidates += $msbuildCommand.Source
}

$programFilesX86 = ${env:ProgramFiles(x86)}
if ($programFilesX86) {
    foreach ($edition in @(
        "BuildTools",
        "Community",
        "Professional",
        "Enterprise"
    )) {
        $msbuildCandidates += Join-Path `
            $programFilesX86 `
            "Microsoft Visual Studio\2022\$edition\MSBuild\Current\Bin\MSBuild.exe"
    }

    $vswherePath = Join-Path `
        $programFilesX86 `
        "Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswherePath -PathType Leaf) {
        $installationPath = & $vswherePath `
            -latest `
            -products * `
            -requires Microsoft.Component.MSBuild `
            -property installationPath
        if ($installationPath) {
            $msbuildCandidates += Join-Path `
                $installationPath `
                "MSBuild\Current\Bin\MSBuild.exe"
        }
    }
}

$msbuildPath = $msbuildCandidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
    Select-Object -First 1

if (-not $msbuildPath) {
    throw (
        "MSBuild was not found. Install Visual Studio 2022 with the " +
        "'Universal Windows Platform development' workload."
    )
}

$packageDirectory = $OutputDirectory.TrimEnd("\") + "\"
$arguments = @(
    $projectPath
    "/t:Rebuild"
    "/m"
    "/p:Configuration=$Configuration"
    "/p:Platform=$Platform"
    "/p:AppxBundle=Never"
    "/p:UapAppxPackageBuildMode=SideloadOnly"
    "/p:AppxPackageDir=$packageDirectory"
    "/p:AppxPackageSigningEnabled=false"
    "/p:GenerateAppxPackageOnBuild=true"
    "/p:GenerateTestArtifacts=true"
    "/p:AppxLogTelemetryFromSideloadingScript=false"
)
if (-not $NoRestore) {
    $arguments += "/restore"
}

$buildStartedAt = Get-Date
Write-Host "MSBuild: $msbuildPath"
Write-Host "Project: $projectPath"
Write-Host "Output: $OutputDirectory"

& $msbuildPath @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Game Bar package build failed with exit code $LASTEXITCODE."
}

$packages = Get-ChildItem `
    -LiteralPath $OutputDirectory `
    -Recurse `
    -File |
    Where-Object {
        $_.Extension -in @(".msix", ".appx") -and
        $_.LastWriteTime -ge $buildStartedAt.AddSeconds(-2)
    }

if (-not $packages) {
    throw "MSBuild succeeded, but no new MSIX or APPX package was produced."
}

Write-Host ""
Write-Host "Game Bar package build complete:"
$packages | ForEach-Object {
    Write-Host "  $($_.FullName)"
}
