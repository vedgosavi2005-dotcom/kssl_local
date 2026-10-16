# SSH tunnel to the VPS database: local port 55460 -> the VPS's 127.0.0.1:5460 (kssl2-db).
#   powershell -File routines\tunnel.ps1     keep this window open while you work; Ctrl+C closes the tunnel
# Host and user come from the gitignored .env (KSSL_VPS_HOST, KSSL_VPS_SSH_USER) or the environment.
$EnvFile = Join-Path $PSScriptRoot "..\.env"
function Get-EnvVal($Name) {
    $v = [Environment]::GetEnvironmentVariable($Name)
    if ($v) { return $v }
    if (Test-Path $EnvFile) {
        $line = Select-String -Path $EnvFile -Pattern "^$Name=" | Select-Object -Last 1
        if ($line) { return ($line.Line -replace "^$Name=", "").Trim("`"'") }
    }
}
$HostIp = Get-EnvVal "KSSL_VPS_HOST"
$SshUser = Get-EnvVal "KSSL_VPS_SSH_USER"
if (-not $HostIp -or -not $SshUser) { Write-Host "set KSSL_VPS_HOST and KSSL_VPS_SSH_USER in .env (see routines/SETUP.md)"; exit 1 }
$Key = Join-Path $env:USERPROFILE ".ssh\kssl_vps"
$LocalPort = 55460
$Remote = "127.0.0.1:5460"

function Test-Up { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $LocalPort); $c.Close(); $true } catch { $false } }

if (-not (Test-Path $Key)) { Write-Host "ssh key not found: $Key (see routines/SETUP.md)"; exit 1 }
if (Test-Up) { Write-Host "port $LocalPort is already open - a tunnel (or something else) is running. Nothing to do."; exit 0 }

$p = Start-Process ssh -NoNewWindow -PassThru -ArgumentList @(
    "-i", "`"$Key`"", "-N", "-L", "${LocalPort}:$Remote", "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=30", "-o", "StrictHostKeyChecking=accept-new", "$SshUser@$HostIp")
try {
    for ($i = 0; $i -lt 20 -and -not (Test-Up); $i++) {
        if ($p.HasExited) { Write-Host "ssh stopped - check the key and the network"; exit 1 }
        Start-Sleep 1
    }
    if (-not (Test-Up)) { Write-Host "port $LocalPort did not open"; exit 1 }
    Write-Host "tunnel open: localhost:$LocalPort -> $HostIp ($Remote).  Keep this window open; Ctrl+C (or close it) to stop."
    $p.WaitForExit()
} finally {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    Write-Host "tunnel closed"
}
