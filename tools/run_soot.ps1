param(
  [string]$ProjectRoot = ".",
  [string]$Output = "tools/output/call_graph.json"
)

# Ensure output directory exists
$dir = Split-Path -Parent $Output
if (-not [string]::IsNullOrEmpty($dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

# Try to locate Git Bash
$bash = $null
try { $bash = (Get-Command bash -ErrorAction Stop) } catch { $bash = $null }
if (-not $bash) {
  Write-Error "Git Bash ('bash') not found on PATH. Please install Git for Windows and ensure bash.exe is available, or run this script from Git Bash: bash tools/run_soot.sh '$ProjectRoot' '$Output'"
  exit 1
}

# Compose and run the bash command
$cmd = "tools/run_soot.sh '" + $ProjectRoot.Replace("'","'\''") + "' '" + $Output.Replace("'","'\''") + "'"
& $bash.Path -lc $cmd
exit $LASTEXITCODE
