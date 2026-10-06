$ErrorActionPreference = 'Stop'
$repoExplorerRoot = Split-Path $PSScriptRoot -Parent
$repoExplorerProcessFile = Join-Path $repoExplorerRoot '.repo-explorer\processes.json'
function Stop-RepoExplorerProcessTree([int]$RepoExplorerProcessId) {
    foreach ($repoExplorerChild in (Get-CimInstance Win32_Process -Filter "ParentProcessId=$RepoExplorerProcessId")) {
        Stop-RepoExplorerProcessTree -RepoExplorerProcessId $repoExplorerChild.ProcessId
    }
    Stop-Process -Id $RepoExplorerProcessId -ErrorAction SilentlyContinue
}
if (Test-Path -LiteralPath $repoExplorerProcessFile) {
    foreach ($repoExplorerEntry in (Get-Content -LiteralPath $repoExplorerProcessFile | ConvertFrom-Json)) {
        $repoExplorerProcess = Get-Process -Id $repoExplorerEntry.Id -ErrorAction SilentlyContinue
        if ($repoExplorerProcess -and $repoExplorerProcess.StartTime.ToUniversalTime() -eq ([datetime]$repoExplorerEntry.Started).ToUniversalTime()) {
            Stop-RepoExplorerProcessTree -RepoExplorerProcessId $repoExplorerProcess.Id
        }
    }
    Remove-Item -LiteralPath $repoExplorerProcessFile
}
