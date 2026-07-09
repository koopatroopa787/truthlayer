# keep_alive.ps1 — restarts main.py automatically on crash
$python = "$PSScriptRoot\.venv\Scripts\python.exe"
$env:PYTHONHOME = $null
$env:PYTHONPATH = $null
Set-Location $PSScriptRoot

while ($true) {
    Write-Host "$(Get-Date -f 'HH:mm:ss') Starting TruthLayer..." -ForegroundColor Cyan
    & $python main.py
    Write-Host "$(Get-Date -f 'HH:mm:ss') Crashed or stopped. Restarting in 5s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
