$ErrorActionPreference = 'Stop'

$logPath = Join-Path $PSScriptRoot 'switch-mysql-service.log'
Start-Transcript -Path $logPath -Append

try {
$mysqld = 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe'
$myini = 'C:\ProgramData\MySQL\MySQL Server 8.0\my.ini'
$binPath = '"' + $mysqld + '" --defaults-file="' + $myini + '" mysql'

if (-not (Test-Path -LiteralPath $mysqld)) {
    throw "Cannot find mysqld.exe at $mysqld"
}

if (-not (Test-Path -LiteralPath $myini)) {
    throw "Cannot find my.ini at $myini"
}

$mysqlService = Get-Service -Name mysql -ErrorAction SilentlyContinue
if ($null -eq $mysqlService) {
    New-Service -Name mysql -BinaryPathName $binPath -DisplayName mysql -StartupType Automatic
} else {
    Set-Service -Name mysql -StartupType Automatic
}

$oldService = Get-Service -Name MySQL80 -ErrorAction SilentlyContinue
if ($oldService -and $oldService.Status -eq 'Running') {
    Stop-Service -Name MySQL80 -Force
    Start-Sleep -Seconds 3
}

if ($oldService) {
    & sc.exe config MySQL80 start= demand
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to set MySQL80 to manual start.'
    }
}

Start-Service -Name mysql
Start-Sleep -Seconds 3

Get-Service -Name mysql,MySQL80 -ErrorAction SilentlyContinue |
    Select-Object Name,DisplayName,Status,StartType |
    Format-Table -AutoSize
} finally {
    Stop-Transcript
}
