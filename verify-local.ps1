$ErrorActionPreference = 'Stop'

Write-Host '1/5 Checking required tools...' -ForegroundColor Cyan
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw 'Docker CLI not found. Install/start Docker Desktop, then reopen PowerShell.'
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw 'Node.js not found. Install Node.js 20+ to run the frontend build locally.'
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw 'npm not found. Repair the Node.js installation.'
}

Write-Host '2/5 Running backend unit tests...' -ForegroundColor Cyan
Push-Location backend
try {
  python -m pip install -r requirements-dev.txt
  python -m pytest -q
} finally { Pop-Location }

Write-Host '3/5 Running frontend production build...' -ForegroundColor Cyan
Push-Location frontend
try {
  npm install
  npm run build
} finally { Pop-Location }

Write-Host '4/5 Building and starting Docker Compose...' -ForegroundColor Cyan
docker compose down
docker compose up --build -d

Write-Host '5/6 Checking API health and January date integrity...' -ForegroundColor Cyan
$health = Invoke-RestMethod 'http://localhost:8000/api/health' -TimeoutSec 10
if ($health.status -ne 'ok') { throw "Health endpoint returned unexpected response: $($health | ConvertTo-Json -Compress)" }
$data = Invoke-RestMethod 'http://localhost:8000/api/analysis?start=2026-01-01&end=2026-01-31&vintage=day-ahead' -TimeoutSec 900
if ($data.rows.Count -ne 744) { throw "Expected 744 hourly rows; got $($data.rows.Count)." }
$badRows = @($data.rows | Where-Object { [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::Parse($_.startTime), 'GMT Standard Time').ToString('yyyy-MM-dd') -notmatch '^2026-01-' })
if ($badRows.Count -gt 0) { throw "Found $($badRows.Count) rows outside January 2026." }
$badVintages = @($data.rows | Where-Object { if ($_.publishTime) { $deliveryDate = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::Parse($_.startTime), 'GMT Standard Time').Date; [DateTimeOffset]::Parse($_.publishTime) -ge [DateTimeOffset]::new($deliveryDate, [TimeSpan]::Zero) } })
if ($badVintages.Count -gt 0) { throw "Found $($badVintages.Count) forecasts published on or after the UTC delivery date." }
if ($data.summary.actualCoveragePct -le 0) { throw 'No actual wind data returned for January 2026.' }
if ($data.summary.forecastCoveragePct -le 0) { throw 'No day-ahead forecast data returned for January 2026.' }
if ($data.summary.pairedPeriods -le 0) { throw 'No paired forecast/actual intervals; accuracy metrics cannot be validated.' }
Write-Host "PASS: day-ahead API returned $($data.rows.Count) January rows, actual coverage $($data.summary.actualCoveragePct)%, forecast coverage $($data.summary.forecastCoveragePct)%, paired intervals $($data.summary.pairedPeriods)." -ForegroundColor Green
Write-Host '6/6 Checking latest-vintage mode...' -ForegroundColor Cyan
$latest = Invoke-RestMethod 'http://localhost:8000/api/analysis?start=2026-01-01&end=2026-01-31&vintage=latest' -TimeoutSec 300
if ($latest.rows.Count -ne 744) { throw "Latest mode expected 744 hourly rows; got $($latest.rows.Count)." }
if ($latest.summary.actualCoveragePct -le 0 -or $latest.summary.forecastCoveragePct -le 0) { throw 'Latest mode returned no actual or forecast data.' }
Write-Host "PASS: latest mode returned 744 rows; $($latest.summary.pairedPeriods) matched periods." -ForegroundColor Green
Write-Host 'Keep Docker running to demo at http://localhost:5173. To stop: docker compose down.' -ForegroundColor Green
