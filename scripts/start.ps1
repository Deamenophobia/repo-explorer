param(
    [ValidateRange(1, 65535)][int]$ApiPort = 8018,
    [ValidateRange(1, 65535)][int]$WebPort = 5178
)
$ErrorActionPreference = 'Stop'
$repoExplorerRoot = Split-Path $PSScriptRoot -Parent
$repoExplorerData = Join-Path $repoExplorerRoot '.repo-explorer'
New-Item -ItemType Directory -Force $repoExplorerData | Out-Null
if ($ApiPort -eq $WebPort) { throw 'API and web ports must be different.' }
foreach ($repoExplorerPort in @($ApiPort, $WebPort)) {
    if (Get-NetTCPConnection -LocalPort $repoExplorerPort -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $repoExplorerPort is already in use. Stop its server before starting Repo Explorer."
    }
}
$repoExplorerPython = Join-Path $repoExplorerRoot '.venv\Scripts\python.exe'
$repoExplorerNode = (Get-Command node.exe).Source
$repoExplorerApi = Start-Process -FilePath $repoExplorerPython -ArgumentList @('-m', 'uvicorn', 'repo_explorer.api:app', '--host', '127.0.0.1', '--port', "$ApiPort") -WorkingDirectory $repoExplorerRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $repoExplorerData 'api.log') -RedirectStandardError (Join-Path $repoExplorerData 'api-error.log')
$repoExplorerPreviousUrl = $env:REPO_EXPLORER_API_URL
$repoExplorerPreviousPort = $env:REPO_EXPLORER_WEB_PORT
try {
    $env:REPO_EXPLORER_API_URL = "http://127.0.0.1:$ApiPort"
    $env:REPO_EXPLORER_WEB_PORT = "$WebPort"
    $repoExplorerWeb = Start-Process -FilePath $repoExplorerNode -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1') -WorkingDirectory (Join-Path $repoExplorerRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $repoExplorerData 'web.log') -RedirectStandardError (Join-Path $repoExplorerData 'web-error.log')
    @(@{ Id = $repoExplorerApi.Id; Started = $repoExplorerApi.StartTime.ToUniversalTime().ToString('o') }, @{ Id = $repoExplorerWeb.Id; Started = $repoExplorerWeb.StartTime.ToUniversalTime().ToString('o') }) | ConvertTo-Json | Set-Content (Join-Path $repoExplorerData 'processes.json')
    Write-Output "Repo Explorer starting: http://127.0.0.1:$WebPort — logs in .repo-explorer/"
} catch {
    Stop-Process -Id $repoExplorerApi.Id -ErrorAction SilentlyContinue
    throw
} finally {
    $env:REPO_EXPLORER_API_URL = $repoExplorerPreviousUrl
    $env:REPO_EXPLORER_WEB_PORT = $repoExplorerPreviousPort
}
