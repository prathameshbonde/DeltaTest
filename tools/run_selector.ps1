Param(
  [string]$ProjectRoot='.',
  [string]$Base='origin/main',
  [string]$Head='HEAD',
  [switch]$DryRun
)

# This PowerShell wrapper will invoke the bash orchestrator. Ensure Git Bash is installed.
$bash = "$Env:ProgramFiles\Git\bin\bash.exe"
if (-not (Test-Path $bash)) { $bash = "bash" }

$argsList = @('tools/run_selector.sh','--project-root',$ProjectRoot,'--base',$Base,'--head',$Head)
if ($DryRun) { $argsList += '--dry-run' }

& $bash -lc ($argsList -join ' ')
