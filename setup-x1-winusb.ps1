[CmdletBinding()]
param(
    [string]$RepoPath = (Get-Location).Path,
    [switch]$SkipPull,
    [switch]$SkipInstall,
    [switch]$SkipMonitor
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest

$X1VidPid = 'VID_17CC&PID_2305'
$F1VidPid = 'VID_17CC&PID_1120'
$ToolsDir = Join-Path $env:LOCALAPPDATA 'MidiWin\Tools'
$BackupDir = Join-Path $env:APPDATA 'MidiWin\driver-backups'
$ZadigPath = Join-Path $ToolsDir 'zadig.exe'
$ZadigIni = Join-Path $ToolsDir 'zadig.ini'
$ZadigPreset = Join-Path $ToolsDir 'Traktor-X1.cfg'

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Get-UsbDevice([string]$VidPid) {
    @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -match [regex]::Escape($VidPid) })
}

function Get-DeviceService([string]$InstanceId) {
    try {
        $property = Get-PnpDeviceProperty -InstanceId $InstanceId `
            -KeyName 'DEVPKEY_Device_Service' -ErrorAction Stop
        return [string]$property.Data
    } catch {
        return ''
    }
}

function Save-DriverSnapshot {
    param([object[]]$Devices)

    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $path = Join-Path $BackupDir "x1-driver-$stamp.json"

    $snapshot = foreach ($device in $Devices) {
        $properties = @{}
        foreach ($key in @(
            'DEVPKEY_Device_Service',
            'DEVPKEY_Device_DriverInfPath',
            'DEVPKEY_Device_DriverProvider',
            'DEVPKEY_Device_DriverVersion',
            'DEVPKEY_Device_DriverDate',
            'DEVPKEY_Device_Manufacturer',
            'DEVPKEY_Device_FriendlyName'
        )) {
            try {
                $properties[$key] = (Get-PnpDeviceProperty `
                    -InstanceId $device.InstanceId `
                    -KeyName $key `
                    -ErrorAction Stop).Data
            } catch {
                $properties[$key] = $null
            }
        }

        [ordered]@{
            CapturedAt = (Get-Date).ToString('o')
            Status = $device.Status
            Class = $device.Class
            FriendlyName = $device.FriendlyName
            InstanceId = $device.InstanceId
            Properties = $properties
        }
    }

    $snapshot | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $path
    Write-Host "Driver snapshot: $path" -ForegroundColor DarkGray
}

function Assert-Repository {
    if (-not (Test-Path (Join-Path $RepoPath 'setup.ps1'))) {
        throw "setup.ps1 was not found in '$RepoPath'. Open PowerShell in the midiwin repository or pass -RepoPath."
    }
    if (-not (Test-Path (Join-Path $RepoPath 'pyproject.toml'))) {
        throw "pyproject.toml was not found in '$RepoPath'."
    }
}

function Update-MidiWin {
    Write-Step 'Updating and installing MIDIWIN'
    Push-Location $RepoPath
    try {
        if (-not $SkipPull) {
            git pull --ff-only
            if ($LASTEXITCODE -ne 0) {
                throw 'git pull --ff-only failed. Resolve local changes before continuing.'
            }
        }
        if (-not $SkipInstall) {
            Set-ExecutionPolicy -Scope Process Bypass -Force
            & (Join-Path $RepoPath 'setup.ps1') -NoStartup
            if ($LASTEXITCODE -ne 0) {
                throw 'MIDIWIN setup failed.'
            }
        }
    } finally {
        Pop-Location
    }
}

function Test-MidiWinX1 {
    $python = Join-Path $RepoPath '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        throw "MIDIWIN Python was not found at '$python'. Run setup.ps1 first."
    }

    Write-Step 'Testing MIDIWIN device discovery'
    $output = & $python -m midiwin --list-devices 2>&1 | Out-String
    Write-Host $output.TrimEnd()
    return ($output -match 'X1 USB bus=.*backend=libusb1')
}

function Get-Zadig {
    Write-Step 'Downloading the official Zadig release'
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

    try {
        $headers = @{ 'User-Agent' = 'MIDIWIN-X1-Setup' }
        $release = Invoke-RestMethod `
            -Headers $headers `
            -Uri 'https://api.github.com/repos/pbatard/libwdi/releases/latest'
        $asset = @($release.assets) |
            Where-Object { $_.name -match '^zadig-.*\.exe$' -and $_.name -notmatch 'debug' } |
            Select-Object -First 1
        if (-not $asset) {
            throw 'The latest official release did not contain a Zadig executable asset.'
        }
        Invoke-WebRequest `
            -Headers $headers `
            -Uri $asset.browser_download_url `
            -OutFile $ZadigPath
    } catch {
        Write-Warning "Direct official download failed: $($_.Exception.Message)"
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Neither the official download nor winget is available.'
        }
        winget install -e --id akeo.ie.Zadig --source winget `
            --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            throw 'winget could not install Zadig.'
        }
        $candidate = @(
            (Get-Command zadig.exe -ErrorAction SilentlyContinue).Source,
            (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\zadig.exe')
        ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
        if (-not $candidate) {
            throw 'Zadig installed, but its executable could not be located.'
        }
        Copy-Item $candidate $ZadigPath -Force
    }

    @'
[general]
advanced_mode = true
exit_on_success = false
log_level = 1

[device]
list_all = true
include_hubs = false
trim_whitespaces = true

[driver]
default_driver = 0
extract_only = false
'@ | Set-Content -Encoding ASCII $ZadigIni

    @'
[device]
Description = "Traktor Kontrol X1"
VID = 0x17CC
PID = 0x2305
'@ | Set-Content -Encoding ASCII $ZadigPreset

    $hash = (Get-FileHash -Algorithm SHA256 $ZadigPath).Hash
    Write-Host "Zadig: $ZadigPath" -ForegroundColor DarkGray
    Write-Host "SHA256: $hash" -ForegroundColor DarkGray
    Write-Host "Preset: $ZadigPreset" -ForegroundColor DarkGray
}

function Wait-ForF1Disconnect {
    $f1 = Get-UsbDevice $F1VidPid
    if ($f1.Count -eq 0) {
        return
    }

    Write-Warning 'The F1 is still connected. Disconnect it now so it cannot be selected accidentally in Zadig.'
    [void](Read-Host 'Press Enter after disconnecting the F1')
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if ((Get-UsbDevice $F1VidPid).Count -eq 0) {
            Write-Host 'F1 disconnected.' -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw 'The F1 is still present. Disconnect it and rerun the script.'
}

function Assert-NoConflictingApplications {
    $patterns = 'Traktor|Controller Editor|Native Access'
    $running = @(Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match $patterns })
    if ($running.Count -eq 0) {
        return
    }

    Write-Warning 'Native Instruments applications are running:'
    $running | Select-Object ProcessName, Id | Format-Table -AutoSize
    [void](Read-Host 'Close those applications, then press Enter')
}

function Invoke-Zadig {
    Write-Step 'Preparing the X1 WinUSB driver switch'
    $instructions = @"
Zadig will open elevated and is preconfigured for:
  - List All Devices
  - WinUSB as the default replacement driver

Inside Zadig, perform exactly these checks:
  1. Select Traktor Kontrol X1.
  2. Confirm USB ID is 17CC:2305.
  3. Confirm the driver on the RIGHT is WinUSB.
  4. Click Replace Driver.
  5. Wait for success, then close Zadig.

Do not select a USB hub, keyboard, mouse, F1, or composite parent.
"@
    Write-Host $instructions -ForegroundColor Yellow

    [void](Read-Host 'Press Enter to launch Zadig as administrator')
    $process = Start-Process -FilePath $ZadigPath -Verb RunAs -PassThru
    $process.WaitForExit()

    Write-Host ''
    Write-Host 'Disconnect and reconnect the X1 now.' -ForegroundColor Yellow
    [void](Read-Host 'Press Enter after the X1 has reconnected')
    Start-Sleep -Seconds 2
}

function Verify-WinUsb {
    Write-Step 'Verifying the X1 driver'
    $devices = Get-UsbDevice $X1VidPid
    if ($devices.Count -eq 0) {
        Write-Warning 'Windows does not currently report the X1. Reconnect it and rerun the script.'
        return $false
    }

    $verified = $false
    foreach ($device in $devices) {
        $service = Get-DeviceService $device.InstanceId
        [pscustomobject]@{
            Name = $device.FriendlyName
            Status = $device.Status
            Service = $service
            InstanceId = $device.InstanceId
        } | Format-List
        if ($service -match '^WinUSB$') {
            $verified = $true
        }
    }

    if (-not $verified) {
        Write-Warning 'The X1 is present, but its active service is not WinUSB.'
        Write-Warning 'Open Zadig again and verify device 17CC:2305 and WinUSB.'
    }
    return $verified
}

Assert-Repository
Update-MidiWin

$x1 = Get-UsbDevice $X1VidPid
if ($x1.Count -eq 0) {
    throw 'Traktor Kontrol X1 (USB ID 17CC:2305) is not present. Connect it and rerun the script.'
}

Save-DriverSnapshot -Devices $x1

if (Test-MidiWinX1) {
    Write-Host 'X1 is already accessible through libusb/WinUSB.' -ForegroundColor Green
} else {
    Assert-NoConflictingApplications
    Wait-ForF1Disconnect
    Get-Zadig
    Invoke-Zadig

    if (-not (Verify-WinUsb)) {
        throw 'WinUSB verification failed. No other driver changes were attempted by this script.'
    }

    if (-not (Test-MidiWinX1)) {
        throw 'WinUSB is active, but MIDIWIN still cannot see the X1. Reboot Windows and rerun with -SkipPull -SkipInstall.'
    }
}

Write-Host "`nX1 setup completed successfully." -ForegroundColor Green
Write-Host 'Reconnect the F1.' -ForegroundColor Yellow

if (-not $SkipMonitor) {
    [void](Read-Host 'Reconnect the F1, then press Enter to start read-only MIDIWIN monitoring')
    $python = Join-Path $RepoPath '.venv\Scripts\python.exe'
    & $python -m midiwin --monitor
}
