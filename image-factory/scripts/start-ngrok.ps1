param(
    [string]$Action = "up",
    [string]$NgrokToken = ""
)

$COMPOSE_FILE = "docker-compose.yml"
$NGROK_COMPOSE = "docker-compose.ngrok.yml"
$ENV_FILE = ".env"

function Write-Header {
    param([string]$Text)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Set-NgrokToken {
    if ($NgrokToken) {
        $envContent = Get-Content $ENV_FILE -Raw
        if ($envContent -match "NGROK_AUTHTOKEN=.*") {
            $envContent = $envContent -replace "NGROK_AUTHTOKEN=.*", "NGROK_AUTHTOKEN=$NgrokToken"
        } else {
            $envContent += "`nNGROK_AUTHTOKEN=$NgrokToken"
        }
        Set-Content -Path $ENV_FILE -Value $envContent
        Write-Host "  Token set in $ENV_FILE" -ForegroundColor Green
    }
}

function Start-WithNgrok {
    Write-Header "Starting ImageFactory with ngrok"

    if ($NgrokToken) {
        Set-NgrokToken
    }

    $ngrokToken = (Select-String -Path $ENV_FILE -Pattern "NGROK_AUTHTOKEN=(.*)").Matches.Groups[1].Value

    if ([string]::IsNullOrWhiteSpace($ngrokToken)) {
        Write-Host "  WARNING: No NGROK_AUTHTOKEN set." -ForegroundColor Yellow
        Write-Host "  Free tier features limited until you set one." -ForegroundColor Yellow
        Write-Host "  Get your token at: https://dashboard.ngrok.com/signup" -ForegroundColor Yellow
        Write-Host "  Set it in .env or pass -NgrokToken <token>" -ForegroundColor Yellow
    }

    Write-Host "  Building and starting all services..." -ForegroundColor Green
    docker compose -f $COMPOSE_FILE -f $NGROK_COMPOSE up -d --build

    if ($LASTEXITCODE -eq 0) {
        Write-Header "Services Status"
        docker compose -f $COMPOSE_FILE -f $NGROK_COMPOSE ps

        Write-Header "Ngrok Dashboard URL"
        Write-Host "  Check tunnels at: http://localhost:4040" -ForegroundColor Green
        Write-Host ""
        Write-Host "  To get the public URL, run:" -ForegroundColor Yellow
        Write-Host "    curl http://localhost:4040/api/tunnels | ConvertFrom-Json | Select-Object -ExpandProperty tunnels" -ForegroundColor Gray
        Write-Host ""
        Write-Host "  Or open http://localhost:4040 in your browser" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Local services:" -ForegroundColor Cyan
        Write-Host "    Dashboard : http://localhost:3000" -ForegroundColor White
        Write-Host "    API       : http://localhost:8000" -ForegroundColor White
        Write-Host "    API Docs  : http://localhost:8000/docs" -ForegroundColor White
        Write-Host "    Ngrok UI  : http://localhost:4040" -ForegroundColor White
    } else {
        Write-Host "  Failed to start services" -ForegroundColor Red
    }
}

function Stop-WithNgrok {
    Write-Header "Stopping ImageFactory with ngrok"
    docker compose -f $COMPOSE_FILE -f $NGROK_COMPOSE down
}

function Get-NgrokUrl {
    Write-Header "Fetching ngrok public URL"
    try {
        $tunnels = curl -s http://localhost:4040/api/tunnels | ConvertFrom-Json
        $url = $tunnels.tunnels | Where-Object { $_.config.addr -eq "http://dashboard:3000" } | Select-Object -ExpandProperty public_url
        if (-not $url) {
            $url = $tunnels.tunnels | Select-Object -First 1 -ExpandProperty public_url
        }
        if ($url) {
            Write-Host "  ngrok URL: $url" -ForegroundColor Green
            Write-Host "  Dashboard accessible at: $url" -ForegroundColor Green
        } else {
            Write-Host "  No active ngrok tunnels found" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  Could not connect to ngrok UI. Is ngrok running?" -ForegroundColor Red
    }
}

switch ($Action.ToLower()) {
    "up" { Start-WithNgrok }
    "down" { Stop-WithNgrok }
    "url" { Get-NgrokUrl }
    "restart" {
        Stop-WithNgrok
        Start-WithNgrok
    }
    default {
        Write-Host "Usage: .\scripts\start-ngrok.ps1 [-Action <up|down|url|restart>] [-NgrokToken <token>]" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  up       - Start all services with ngrok (default)" -ForegroundColor White
        Write-Host "  down     - Stop all services" -ForegroundColor White
        Write-Host "  url      - Get the current ngrok public URL" -ForegroundColor White
        Write-Host "  restart  - Restart all services" -ForegroundColor White
        Write-Host ""
        Write-Host "  -NgrokToken <token>  - Set your ngrok auth token (optional, get at https://dashboard.ngrok.com/signup)" -ForegroundColor Gray
    }
}
