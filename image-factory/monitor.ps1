$token = "nb1JECCQlJxaRdW6TTu3ES5M8yV2PfYuHJw26o4xORc"
$baseUrl = "http://localhost:8000"
$headers = @{ Authorization = "Bearer $token" }
$iteration = 0
$maxIterations = 10
$delaySeconds = 15
$projectRoot = "C:\Users\KATEB\Documents\Hichem-AI\image-factory"

$previousStats = $null
$previousQueue = $null
$previousSmoke = $null
$initialized = $false

function Get-Timestamp { Get-Date -Format "HH:mm:ss" }

function Get-Stats { try { Invoke-RestMethod -Uri "$baseUrl/api/v1/dashboard/stats" -Headers $headers -ErrorAction Stop } catch { Write-Warning "Stats endpoint failed: $_"; return $null } }

function Get-Queue { try { Invoke-RestMethod -Uri "$baseUrl/api/v1/dashboard/queue" -Headers $headers -ErrorAction Stop } catch { Write-Warning "Queue endpoint failed: $_"; return $null } }

function Get-SmokeTest { try { Invoke-RestMethod -Uri "$baseUrl/api/v1/verification/smoke-test/status" -Headers $headers -ErrorAction Stop } catch { Write-Warning "Smoke-test endpoint failed: $_"; return $null } }

function Get-WorkerLogs { try { $logs = & docker compose logs --tail=10 worker 2>&1 | Out-String; return $logs } catch { return "Could not fetch worker logs: $_" } }

function Compare-And-Log {
    param($stats, $queue, $smoke)

    $ts = Get-Timestamp

    if ($stats) {
        Write-Host "[$ts] STATS total=$($stats.total_products) completed=$($stats.products_completed) failed=$($stats.products_failed) processing=$($stats.products_processing)"
    }
    if ($queue) {
        Write-Host "[$ts] QUEUE active=$($queue.active_jobs) waiting=$($queue.waiting_jobs) est_completion=$($queue.estimated_completion_minutes) min"
    }
    if ($smoke) {
        Write-Host "[$ts] SMOKE status=$($smoke.status) last_run=$($smoke.last_run_at)"
    }
}

function Detect-Changes {
    param($stats, $queue)
    $ts = Get-Timestamp
    $changes = @()

    if (-not $initialized) { return }

    if ($stats -and $previousStats) {
        if ($stats.total_products -ne $previousStats.total_products) {
            $diff = $stats.total_products - $previousStats.total_products
            $changes += "NEW PRODUCTS: +$diff (now $($stats.total_products))"
        }
        if ($stats.products_completed -ne $previousStats.products_completed) {
            $diff = $stats.products_completed - $previousStats.products_completed
            $changes += "COMPLETED: +$diff (now $($stats.products_completed))"
        }
        if ($stats.products_failed -ne $previousStats.products_failed) {
            $diff = $stats.products_failed - $previousStats.products_failed
            $changes += "FAILURES: +$diff (now $($stats.products_failed))"
        }
        if ($stats.products_processing -ne $previousStats.products_processing) {
            $diff = $stats.products_processing - $previousStats.products_processing
            if ($diff -gt 0) { $changes += "PROCESSING: +$diff started (now $($stats.products_processing))" }
            else { $changes += "PROCESSING: $diff finished (now $($stats.products_processing))" }
        }
    }

    if ($queue -and $previousQueue) {
        if ($queue.active_jobs -ne $previousQueue.active_jobs) {
            $changes += "ACTIVE JOBS: $($previousQueue.active_jobs) -> $($queue.active_jobs)"
        }
        if ($queue.waiting_jobs -ne $previousQueue.waiting_jobs) {
            $changes += "WAITING JOBS: $($previousQueue.waiting_jobs) -> $($queue.waiting_jobs)"
        }
    }

    if ($changes.Count -gt 0) {
        Write-Host "  >> CHANGE DETECTED: $($changes -join ' | ')" -ForegroundColor Yellow
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ImageFactory Monitor" -ForegroundColor Cyan
Write-Host "  Polling every ${delaySeconds}s for $maxIterations iterations" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

while ($iteration -lt $maxIterations) {
    $iteration++
    Write-Host "`n--- Iteration $iteration/$maxIterations ---" -ForegroundColor Cyan

    $stats = Get-Stats
    $queue = Get-Queue
    $smoke = Get-SmokeTest

    Compare-And-Log $stats $queue $smoke
    Detect-Changes $stats $queue

    $previousStats = $stats
    $previousQueue = $queue
    $previousSmoke = $smoke
    $initialized = $true

    $logs = Get-WorkerLogs
    if ($logs -match "ERROR|error|CRITICAL|Exception|Traceback|captcha|CAPTCHA|fail|FAIL") {
        Write-Host "  >> WORKER ANOMALY DETECTED in logs:" -ForegroundColor Red
        $logs -split "`n" | ForEach-Object { if ($_ -match "ERROR|error|CRITICAL|Exception|Traceback|captcha|CAPTCHA|fail|FAIL") { Write-Host "     $_" -ForegroundColor Red } }
    } else {
        Write-Host "  Worker logs: clean" -ForegroundColor Green
    }

    if ($iteration -lt $maxIterations) {
        Start-Sleep -Seconds $delaySeconds
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  MONITORING COMPLETE - FINAL SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Started at: (first poll)"
Write-Host "Ended at: $(Get-Timestamp)"
if ($stats) {
    Write-Host "Final Stats: total=$($stats.total_products) completed=$($stats.products_completed) failed=$($stats.products_failed) processing=$($stats.products_processing)"
}
if ($queue) {
    Write-Host "Final Queue: active=$($queue.active_jobs) waiting=$($queue.waiting_jobs) est=$($queue.estimated_completion_minutes) min"
}
Write-Host "Overall system health: " -NoNewline
if ($stats -and $stats.products_failed -gt 0) { Write-Host "WARNING (failures detected)" -ForegroundColor Yellow }
elseif ($queue -and $queue.waiting_jobs -gt 10) { Write-Host "DEGRADED (queue backlog)" -ForegroundColor Yellow }
elseif ($stats -and $stats.products_processing -gt 0) { Write-Host "NORMAL (actively processing)" -ForegroundColor Green }
else { Write-Host "IDLE" -ForegroundColor Gray }
