[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoDialog
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $repoRoot '.runtime-logs'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

# Codex and some IDE terminals can expose both Path and PATH. Start-Process treats
# them as duplicate keys, so normalize the process environment before launching.
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
[Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
[Environment]::SetEnvironmentVariable('Path', "$machinePath;$userPath", 'Process')

function Write-Step {
    param([string]$Message)

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message" -ForegroundColor Cyan
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutMilliseconds = 500
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne($TimeoutMilliseconds)) {
            return $false
        }

        $client.EndConnect($connection)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-TcpPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Resolve-CommandPath {
    param(
        [Parameter(Mandatory = $true)][string]$PreferredPath,
        [Parameter(Mandatory = $true)][string]$CommandName
    )

    if (Test-Path -LiteralPath $PreferredPath) {
        return $PreferredPath
    }

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Cannot find $CommandName. Expected path: $PreferredPath"
    }

    return $command.Source
}

function Start-LoggedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )

    $stdoutPath = Join-Path $logRoot "$Name-$timestamp.out.log"
    $stderrPath = Join-Path $logRoot "$Name-$timestamp.err.log"

    Write-Step "Starting $Name..."
    return Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru
}

function Start-WindowsServiceForPort {
    param(
        [Parameter(Mandatory = $true)][string]$DisplayLabel,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string[]]$ServiceNames
    )

    if (Test-TcpPort -Port $Port) {
        Write-Step "$DisplayLabel is already available on port $Port."
        return
    }

    foreach ($serviceName in $ServiceNames) {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($null -eq $service) {
            continue
        }

        if ($service.Status -ne 'Running') {
            Write-Step "Starting Windows service $serviceName..."
            Start-Service -Name $serviceName
        }

        if (Wait-TcpPort -Port $Port -TimeoutSeconds 15) {
            return
        }
    }

    throw "$DisplayLabel did not become available on port $Port."
}

function Add-ServiceResult {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $ready = Wait-TcpPort -Port $Port -TimeoutSeconds $TimeoutSeconds
    $Results.Add([pscustomobject]@{
        Name = $Name
        Port = $Port
        Ready = $ready
    })

    if ($ready) {
        Write-Host "  OK  $Name (port $Port)" -ForegroundColor Green
    } else {
        Write-Host "  FAIL  $Name (port $Port)" -ForegroundColor Red
    }
}

$results = New-Object 'System.Collections.Generic.List[object]'

try {
    Write-Step 'Checking database services...'
    Start-WindowsServiceForPort -DisplayLabel 'MySQL' -Port 3306 -ServiceNames @('mysql', 'mysqlzt', 'MySQL80')
    Start-WindowsServiceForPort -DisplayLabel 'Redis' -Port 6379 -ServiceNames @('rediszt3', 'Redis')

    $pythonPath = Join-Path $repoRoot 'ai\travel_agent\.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "Python virtual environment is missing: $pythonPath"
    }

    $mavenPath = Resolve-CommandPath `
        -PreferredPath 'C:\develop\apache-maven-3.9.11\bin\mvn.cmd' `
        -CommandName 'mvn.cmd'
    $npmPath = Resolve-CommandPath `
        -PreferredPath 'C:\develop\npm.cmd' `
        -CommandName 'npm.cmd'

    if (-not (Test-TcpPort -Port 8000)) {
        Start-LoggedProcess `
            -Name 'fastapi' `
            -FilePath $pythonPath `
            -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
            -WorkingDirectory (Join-Path $repoRoot 'ai\travel_agent') | Out-Null
    } else {
        Write-Step 'FastAPI is already running.'
    }

    if (-not (Test-TcpPort -Port 8080)) {
        $jdkHome = 'C:\Users\20343\.jdks\ms-17.0.17'
        $previousJavaHome = $env:JAVA_HOME
        $previousPath = $env:Path
        try {
            if (Test-Path -LiteralPath (Join-Path $jdkHome 'bin\java.exe')) {
                $env:JAVA_HOME = $jdkHome
                $env:Path = "$jdkHome\bin;$previousPath"
            }

            Start-LoggedProcess `
                -Name 'spring-boot' `
                -FilePath $mavenPath `
                -ArgumentList @('spring-boot:run', '-s', 'maven-settings.xml') `
                -WorkingDirectory (Join-Path $repoRoot 'backend') | Out-Null
        } finally {
            $env:Path = $previousPath
            if ($null -eq $previousJavaHome) {
                Remove-Item Env:JAVA_HOME -ErrorAction SilentlyContinue
            } else {
                $env:JAVA_HOME = $previousJavaHome
            }
        }
    } else {
        Write-Step 'Spring Boot is already running.'
    }

    if (-not (Test-TcpPort -Port 5173)) {
        Start-LoggedProcess `
            -Name 'frontend' `
            -FilePath $npmPath `
            -ArgumentList @('run', 'dev') `
            -WorkingDirectory (Join-Path $repoRoot 'frontend') | Out-Null
    } else {
        Write-Step 'User frontend is already running.'
    }

    if (-not (Test-TcpPort -Port 5174)) {
        Start-LoggedProcess `
            -Name 'frontend-admin' `
            -FilePath $npmPath `
            -ArgumentList @('run', 'dev') `
            -WorkingDirectory (Join-Path $repoRoot 'frontend-admin') | Out-Null
    } else {
        Write-Step 'Admin frontend is already running.'
    }

    Write-Step 'Waiting for services to become ready...'
    Add-ServiceResult -Results $results -Name 'MySQL' -Port 3306 -TimeoutSeconds 10
    Add-ServiceResult -Results $results -Name 'Redis' -Port 6379 -TimeoutSeconds 10
    Add-ServiceResult -Results $results -Name 'FastAPI' -Port 8000 -TimeoutSeconds 120
    Add-ServiceResult -Results $results -Name 'Spring Boot' -Port 8080 -TimeoutSeconds 120
    Add-ServiceResult -Results $results -Name 'User frontend' -Port 5173 -TimeoutSeconds 30
    Add-ServiceResult -Results $results -Name 'Admin frontend' -Port 5174 -TimeoutSeconds 30

    $failedServices = @($results | Where-Object { -not $_.Ready })
    if ($failedServices.Count -gt 0) {
        $failedNames = ($failedServices | ForEach-Object { $_.Name }) -join ', '
        throw "Some services failed to start: $failedNames. Check logs in $logRoot"
    }

    if (-not $NoBrowser) {
        Write-Step 'Opening the user app and admin console...'
        Start-Process 'http://127.0.0.1:5173'
        Start-Process 'http://127.0.0.1:5174'
    }

    $message = @"
All OneClick Trip services are ready.

User app:  http://127.0.0.1:5173
Admin:     http://127.0.0.1:5174
FastAPI:   http://127.0.0.1:8000/docs
Spring:    http://127.0.0.1:8080

Logs: $logRoot
"@

    if (-not $NoDialog) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            $message,
            'OneClick Trip Launcher',
            [System.Windows.MessageBoxButton]::OK,
            [System.Windows.MessageBoxImage]::Information
        ) | Out-Null
    }
} catch {
    $errorMessage = $_.Exception.Message
    Write-Host "Startup failed: $errorMessage" -ForegroundColor Red

    if (-not $NoDialog) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            "Startup failed.`n`n$errorMessage`n`nLogs: $logRoot",
            'OneClick Trip Launcher',
            [System.Windows.MessageBoxButton]::OK,
            [System.Windows.MessageBoxImage]::Error
        ) | Out-Null
    }
    exit 1
}
