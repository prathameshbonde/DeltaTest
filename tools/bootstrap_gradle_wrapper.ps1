Param(
  [string]$GradlePropsPath = "gradle/wrapper/gradle-wrapper.properties"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $GradlePropsPath)) {
  Write-Error "Properties file not found: $GradlePropsPath"
}

$props = Get-Content $GradlePropsPath | Where-Object { $_ -match '^\s*distributionUrl=' }
if (-not $props) { Write-Error "distributionUrl not found in $GradlePropsPath" }
$url = $props -replace '^\s*distributionUrl=', ''
$url = $url -replace '\\:', ':'

$outDir = Join-Path $PSScriptRoot '..\gradle\wrapper' | Resolve-Path
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$jarPath = Join-Path $outDir 'gradle-wrapper.jar'

Write-Host "Downloading Gradle distribution from $url ..."
$tmpZip = [System.IO.Path]::GetTempFileName() | ForEach-Object { $_ + '.zip' }
Invoke-WebRequest -Uri $url -OutFile $tmpZip

$expandDir = Join-Path ([System.IO.Path]::GetTempPath()) ("gradle-dist-" + [System.Guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $expandDir | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($tmpZip, $expandDir)

$wrapperJar = Get-ChildItem -Path $expandDir -Recurse -Filter 'gradle-wrapper-*.jar' | Select-Object -First 1
if (-not $wrapperJar) { Write-Error "Could not find gradle-wrapper-*.jar in distribution." }

Copy-Item $wrapperJar.FullName -Destination $jarPath -Force
Write-Host "Wrote $jarPath"

Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
Remove-Item $expandDir -Recurse -Force -ErrorAction SilentlyContinue
