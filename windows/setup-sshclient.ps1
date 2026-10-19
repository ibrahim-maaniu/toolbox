<#
.SYNOPSIS
    Sets up an SSH client key + ~/.ssh/config alias for connecting to a pubkey-only server.

.DESCRIPTION
    - Generates an ed25519 keypair if missing
    - Writes a Host alias into ~/.ssh/config
    - Prints the public key and copies it to clipboard for manual handoff

    Uses only native PowerShell cmdlets for ACL management (no icacls/takeown).

.PARAMETER KeyType
    Key type to generate (default ed25519).

.PARAMETER HostName
    IP or hostname of the SSH server.

.PARAMETER Username
    Login user on the SSH server.

.PARAMETER Port
    SSH port (default 22).

.PARAMETER Alias
    Short name for `ssh <alias>` (default "remote").

.EXAMPLE
    .\setup-sshclient.ps1 -HostName 203.0.113.42 -Username alice -Port 2222 -Alias mydevice
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$HostName,
    [Parameter(Mandatory = $true)] [string]$Username,
    [int]$Port = 22,
    [string]$Alias = 'remote',
    [string]$KeyType = 'ed25519'
)

$ErrorActionPreference = 'Stop'

# --- Output helpers -------------------------------------------------------
function Write-Step  ($m){ Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok    ($m){ Write-Host "    $m" -ForegroundColor Green }
function Write-Warn2 ($m){ Write-Host "    $m" -ForegroundColor Yellow }

$script:Me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

function Set-FileAcl {
    <#
    .SYNOPSIS
        Applies an ACL to a file or directory.

    .DESCRIPTION
        Get-Acl -> mutate in memory -> Set-Acl. Set-Acl replaces the whole
        descriptor, which is why the Get is mandatory.

    .PARAMETER Path
        File or directory to modify.

    .PARAMETER Rights
        Rights to grant to the current user (e.g. "Read,Write").
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [System.Security.AccessControl.FileSystemRights]$Rights,
        [switch]$PreserveInheritance
    )
    $acl = Get-Acl -LiteralPath $Path

    if ($PreserveInheritance) {
        $acl.SetAccessRuleProtection($false, $true)
    } else {
        $acl.SetAccessRuleProtection($true, $false)
    }

    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $script:Me,
        $Rights,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $acl.SetAccessRule($rule)
    [System.IO.FileSystemAclExtensions]::SetAccessControl($Path, $acl)
}

Write-Step "Checking OpenSSH client..."
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Write-Warn2 "ssh not found. Installing OpenSSH.Client capability..."
    $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Client*'
    if ($cap.State -ne 'Installed') {
        Add-WindowsCapability -Online -Name $cap.Name | Out-Null
    }
}
Write-Ok "Client: $((& ssh -V 2>&1) -join ' ')"

$sshDir = Join-Path $env:USERPROFILE '.ssh'
if (-not (Test-Path $sshDir)) {
    New-Item -ItemType Directory -Path $sshDir | Out-Null
    Write-Ok "Created $sshDir"
}

Set-FileAcl -Path $sshDir -Rights 'FullControl' -PreserveInheritance
Write-Ok "Locked down $sshDir"

$keyPath = Join-Path $sshDir 'id_ed25519'
$pubPath = "$keyPath.pub"

if (-not (Test-Path $keyPath)) {
    Write-Step "Generating $KeyType keypair..."
    # -N '""' = empty passphrase; ssh-keygen parses this literally on Windows
    & ssh-keygen -t $KeyType -C "$Username@$([Environment]::MachineName)" -f $keyPath -N '' | Out-Null
    Write-Ok "Key created: $keyPath"
} else {
    Write-Ok "Existing key at $keyPath — reusing."
}

$pubKey = (Get-Content -LiteralPath $pubPath -Raw).Trim()

Set-FileAcl -Path $keyPath -Rights 'Read' -PreserveInheritance
Write-Ok "Restricted ACL on private key"

Write-Step "Writing ~/.ssh/config alias '$Alias'..."
$configPath = Join-Path $sshDir 'config'
if (-not (Test-Path $configPath)) {
    New-Item -ItemType File -Path $configPath | Out-Null
}

$configText = Get-Content -LiteralPath $configPath -Raw -ErrorAction SilentlyContinue
if ($configText -match "(?m)^\s*Host\s+$([regex]::Escape($Alias))\s*$") {
    Write-Ok "Alias '$Alias' already exists in config — leaving as is."
} else {
    $block = @"

Host $Alias
    HostName $HostName
    User $Username
    Port $Port
    IdentityFile ~/.ssh/id_${KeyType}
    IdentitiesOnly yes
    ServerAliveInterval 60
"@
    Add-Content -LiteralPath $configPath -Value $block -Encoding ascii
    Set-FileAcl -Path $configPath -Rights 'Read,Write' -PreserveInheritance
    Write-Ok "Alias added to $configPath"
}

try {
    Set-Clipboard -Value $pubKey
    Write-Ok "Public key copied to clipboard."
} catch {
    Write-Warn2 "Could not copy to clipboard: $_"
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Magenta
Write-Host "  ONE STEP REMAINING" -ForegroundColor Magenta
Write-Host "=====================================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Your public key:" -ForegroundColor Cyan
Write-Host "    $pubKey" -ForegroundColor White
Write-Host ""
Write-Host "  Send the line above to the server operator out-of-band" -ForegroundColor Yellow
Write-Host "  (Slack, email, Signal, etc.). It's also in your clipboard." -ForegroundColor Yellow
Write-Host ""
Write-Host "  Once they confirm it's added, connect with:" -ForegroundColor Yellow
Write-Host "    ssh $Alias" -ForegroundColor White
Write-Host ""