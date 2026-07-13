$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $name = $parts[0].Trim()
            $value = $parts[1].Trim().Trim("'").Trim('"')
            if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
                [Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
    }
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv .venv
}

& $Python -c "import fastapi" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing UI dependencies..."
    & $Python -m pip install -r requirements.txt
}

if (-not $env:UI_HOST) { $env:UI_HOST = "127.0.0.1" }
if (-not $env:UI_PORT) { $env:UI_PORT = "8765" }
$env:PYTHONPATH = $Root

Write-Host ""
Write-Host "  TDengine Migration Studio"
Write-Host "  Open http://$($env:UI_HOST):$($env:UI_PORT)"
Write-Host ""

& $Python -m agentic_pi_migration.web.server
