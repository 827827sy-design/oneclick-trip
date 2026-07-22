[CmdletBinding()]
param(
    [switch]$RequireChroma
)

$ErrorActionPreference = 'Stop'
$checks = New-Object 'System.Collections.Generic.List[object]'

function Add-TcpCheck {
    param([string]$Name, [int]$Port, [bool]$Required = $true)

    $client = New-Object System.Net.Sockets.TcpClient
    $ok = $false
    try {
        $pending = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if ($pending.AsyncWaitHandle.WaitOne(800)) {
            $client.EndConnect($pending)
            $ok = $true
        }
    } catch {
        $ok = $false
    } finally {
        $client.Close()
    }
    $checks.Add([pscustomobject]@{ Name = $Name; Target = "tcp://127.0.0.1:$Port"; Required = $Required; Ready = $ok })
}

function Add-HttpCheck {
    param([string]$Name, [string]$Url, [bool]$Required = $true)

    $ok = $false
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        $ok = $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        $ok = $false
    }
    $checks.Add([pscustomobject]@{ Name = $Name; Target = $Url; Required = $Required; Ready = $ok })
}

Add-TcpCheck -Name 'MySQL' -Port 3306
Add-TcpCheck -Name 'Redis' -Port 6379
Add-HttpCheck -Name 'FastAPI health' -Url 'http://127.0.0.1:8000/health'
Add-HttpCheck -Name 'Spring Boot API' -Url 'http://127.0.0.1:8080/api/cities'
Add-HttpCheck -Name 'User frontend' -Url 'http://127.0.0.1:5173'
Add-HttpCheck -Name 'Admin frontend' -Url 'http://127.0.0.1:5174'
Add-HttpCheck -Name 'Chroma heartbeat' -Url 'http://127.0.0.1:8001/api/v2/heartbeat' -Required $RequireChroma.IsPresent

$checks | Format-Table Name, Target, Required, Ready -AutoSize
$failed = @($checks | Where-Object { $_.Required -and -not $_.Ready })
if ($failed.Count -gt 0) {
    Write-Host "`nVerification failed: $($failed.Name -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "`nOneClick Trip integration environment is ready." -ForegroundColor Green
