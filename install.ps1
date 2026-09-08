<#
    Namesti bliznjico "Urnik STPS" v meni Start (in po zelji na namizje).

    Uporaba:
        powershell -ExecutionPolicy Bypass -File .\install.ps1
        powershell -ExecutionPolicy Bypass -File .\install.ps1 -Desktop
        powershell -ExecutionPolicy Bypass -File .\install.ps1 -Yes       # brez vprasanj
        powershell -ExecutionPolicy Bypass -File .\install.ps1 -Remove

    Ce Pythona ni, skripta ponudi namestitev prek winget.

    Bliznjica kaze na to mapo, zato je po namestitvi ne premikaj -
    ce jo premaknes, skripto preprosto pozeni znova.
#>

[CmdletBinding()]
param(
    [switch]$Desktop,
    [switch]$Remove,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'

# Ime z znakom S-caron zapisemo prek kode, da je skripta cisti ASCII.
$AppName   = "Urnik STP" + [char]0x0160          # Urnik STPS
$Root      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script    = Join-Path $Root 'stps_urnik.py'
$IconPath  = Join-Path $Root 'assets\urnik.ico'
$StartMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$Targets   = @((Join-Path $StartMenu "$AppName.lnk"))
if ($Desktop -or $Remove) {
    $Targets += (Join-Path ([Environment]::GetFolderPath('Desktop')) "$AppName.lnk")
}

if ($Remove) {
    foreach ($t in $Targets) {
        if (Test-Path $t) { Remove-Item $t -Force; "Odstranjeno: $t" }
    }
    "Koncano."
    return
}

# --- iskanje Pythona ------------------------------------------------------
# Windows ima v mapi WindowsApps prazne (0 bajtov) nadomestke, ki samo odprejo
# Trgovino. Prave datoteke locimo po velikosti.
function Test-RealExe($path) {
    if (-not $path) { return $false }
    if (-not (Test-Path $path)) { return $false }
    return (Get-Item $path).Length -gt 0
}

function Find-Pythonw {
    foreach ($c in @(Get-Command pythonw.exe -All -ErrorAction SilentlyContinue)) {
        if (Test-RealExe $c.Source) { return $c.Source }
    }
    foreach ($c in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
        if (-not (Test-RealExe $c.Source)) { continue }
        $cand = Join-Path (Split-Path -Parent $c.Source) 'pythonw.exe'
        if (Test-RealExe $cand) { return $cand }
    }
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        try {
            $base = & py.exe -3 -c "import sys; print(sys.base_prefix)" 2>$null
            if ($base) {
                $cand = Join-Path $base.Trim() 'pythonw.exe'
                if (Test-RealExe $cand) { return $cand }
            }
        } catch { }
    }
    # Python je lahko namescen, a ni na poti (npr. takoj po namestitvi).
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        (Join-Path $env:ProgramFiles 'Python'),
        ${env:ProgramFiles(x86)},
        'C:\'
    ) | Where-Object { $_ -and (Test-Path $_) }
    foreach ($r in $roots) {
        $hit = Get-ChildItem -Path $r -Filter 'Python3*' -Directory -ErrorAction SilentlyContinue |
               Sort-Object Name -Descending |
               ForEach-Object { Join-Path $_.FullName 'pythonw.exe' } |
               Where-Object { Test-RealExe $_ } |
               Select-Object -First 1
        if ($hit) { return $hit }
    }
    return $null
}

$Pythonw = Find-Pythonw

if (-not $Pythonw) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    $doInstall = $false
    if ($winget) {
        if ($Yes) {
            $doInstall = $true
        } else {
            ""
            "Python 3 ni namescen - Urnik ga potrebuje za delovanje."
            $ans = Read-Host "Naj ga namestim zdaj (winget)? [d/N]"
            $doInstall = $ans -match '^(d|D|y|Y)'
        }
    }

    if ($doInstall) {
        "Namescam Python 3 ..."
        & winget.exe install --id Python.Python.3.12 --scope user `
            --accept-source-agreements --accept-package-agreements --silent
        $Pythonw = Find-Pythonw
    }

    if (-not $Pythonw) {
        ""
        "Pythona ni bilo mogoce najti. Namesti ga na enega od nacinov:"
        "   winget install Python.Python.3.12"
        "   ali s strani https://www.python.org/downloads/windows/"
        "      (pri namestitvi obkljukaj 'Add python.exe to PATH')"
        ""
        "Nato znova pozeni to skripto."
        throw "Python 3 ni na voljo."
    }
}

if (-not (Test-Path $Script)) {
    throw "Ni mogoce najti $Script - skripto pozeni iz mape, kjer je aplikacija."
}

# --- ikona ----------------------------------------------------------------
if (-not (Test-Path $IconPath)) {
    $python = $Pythonw -replace 'pythonw\.exe$', 'python.exe'
    if (-not (Test-Path $python)) { $python = $Pythonw }
    & $python (Join-Path $Root 'make_icon.py') | Out-Null
}

# --- bliznjice ------------------------------------------------------------
$shell = New-Object -ComObject WScript.Shell
foreach ($t in $Targets) {
    $dir = Split-Path -Parent $t
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    $lnk = $shell.CreateShortcut($t)
    $lnk.TargetPath       = $Pythonw
    $lnk.Arguments        = '"{0}"' -f $Script
    $lnk.WorkingDirectory = $Root
    $lnk.Description      = 'Urnik, nadomescanja in odpadle ure - STPS Trbovlje'
    $lnk.WindowStyle      = 7          # zagon pomanjsano, okno odpre Edge
    if (Test-Path $IconPath) { $lnk.IconLocation = "$IconPath,0" }
    $lnk.Save()
    "Ustvarjeno: $t"
}
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null

""
"Python:   $Pythonw"
"Program:  $Script"
""
"Se zadnji korak: pritisni tipko Windows, vtipkaj ""$AppName"","
"nato z desnim klikom izberi ""Pripni na zacetni zaslon"" (Pin to Start)."
