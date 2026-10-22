Write-host "Starting Windows 11 Setup..." -ForegroundColor Cyan

Write-Host "Installing essential applications..." -ForegroundColor Yellow
$apps = @(
    "Bitwarden.Bitwarden",
    "Eugeny.Tabby",
    "Git.Git",
    "Parsec.ParsecVDD",
    "Daum.PotPlayer",
    "Waterfox.Waterfox",
    "RARLab.WinRAR",
    "Microsoft.VCRedist.2010.x64",
    "Logitech.GHUB",
    "OBSProject.OBSStudio",
    "Parsec.Parsec",
    "Valve.Steam",
    "Ubisoft.Connect",
    "WiresharkFoundation.Wireshark",
    "Microsoft.VCRedist.2013.x64",
    "Microsoft.VCRedist.2015+.x64",
    "Microsoft.VCRedist.2012.x86",
    "Microsoft.PowerShell",
    "Microsoft.VCRedist.2015+.x86",
    "Microsoft.VCRedist.2013.x86",
    "Famatech.AdvancedIPScanner",
    "Microsoft.VCRedist.2010.x86",
    "ElectronicArts.EADesktop",
    "Microsoft.VCRedist.2012.x64",
    "Discord.Discord",
    "Microsoft.Sysinternals.Suite",
    "MongoDB.Compass.Full",
    "Rufus.Rufus",
    "Netflix",
    "WhatsApp",
    "Anthropic.Claude",
    "Gimp.Gimp",
    "Microsoft.DotNet.Runtime.10",
    "Microsoft.DotNet.Native.Runtime",
    "Microsoft.VisualStudioCode",
    "Microsoft.WindowsTerminal",
    "Microsoft.WSL",
    "Spotify.Spotify",
    "Telegram.TelegramDesktop",
    "Mega.MEGASync",
    "AntibodySoftware.WizTree",
    "JanDeDobbeleer.OhMyPosh",
    "REALiX.hwinfo",
    "CPUID.HWMonitor"
)

foreach ($app in $apps) {
    Write-Host "Installing $app..." -ForegroundColor Yellow
    winget install $app -e  --accept-source-agreements --accept-package-agreements --silent
}

Write-Host "Disabling Telemetry and Ads..." -ForegroundColor Yellow
# Disable Telemetry and Ads
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo" -Name "Enabled" -Value 0 -Type DWord -Force
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Siuf\Rules" -Name "NumberOfSIUFInPeriod" -Value 0 -Type DWord -Force

Write-Host "Removing some pre-installed apps..." -ForegroundColor Yellow
$bloaters = @(
    "Microsoft.3DBuilder",
    "Microsoft.BingWeather",
    "Microsoft.GetHelp",
    "Microsoft.Getstarted",
    "Microsoft.Microsoft3DViewer",
    "Microsoft.MicrosoftOfficeHub",
    "Microsoft.MicrosoftSolitaireCollection",
    "Microsoft.MicrosoftStickyNotes",
    "Microsoft.MixedReality.Portal",
    "Microsoft.Office.OneNote",
    "Microsoft.People",
    "Microsoft.Print3D",
    "Microsoft.SkypeApp",
    "Microsoft.Xbox.TCUI",
    "Microsoft.XboxApp",
    "Microsoft.XboxGameOverlay",
    "Microsoft.XboxGamingOverlay",
    "Microsoft.XboxIdentityProvider",
    "Microsoft.XboxSpeechToTextOverlay",
    "Microsoft.YourPhone"
)

foreach ($bloat in $bloaters) {
    Write-Host "Removing $bloat..." -ForegroundColor Yellow
    Get-AppxPackage -Name $bloat | Remove-AppxPackage -ErrorAction SilentlyContinue
}

Write-host "Windows 11 Setup completed!" -ForegroundColor Green