<#
    Zapakira aplikacijo v en sam ZIP, ki ga lahko posljes naprej.

    Uporaba:
        powershell -ExecutionPolicy Bypass -File .\pack.ps1
        powershell -ExecutionPolicy Bypass -File .\pack.ps1 -Out D:\prenos
#>

[CmdletBinding()]
param(
    [string]$Out = [Environment]::GetFolderPath('Desktop')
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Name = 'Urnik-STPS'
$Zip  = Join-Path $Out "$Name.zip"

# V paket gre samo tisto, kar aplikacija potrebuje - brez predpomnilnika,
# prevedenih datotek in prejsnjih paketov.
$Include = @(
    'ZAZENI.txt',
    'Namesti.bat',
    'install.ps1',
    'stps_urnik.py',
    'urnik_source.py',
    'make_icon.py',
    'README.md',
    'assets',
    'web'
)

$stage = Join-Path ([System.IO.Path]::GetTempPath()) "$Name-$(Get-Random)"
New-Item -ItemType Directory -Path (Join-Path $stage $Name) -Force | Out-Null
$dest = Join-Path $stage $Name

foreach ($item in $Include) {
    $src = Join-Path $Root $item
    if (-not (Test-Path $src)) { continue }
    Copy-Item $src -Destination $dest -Recurse -Force
}
Get-ChildItem $dest -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path $dest -DestinationPath $Zip -CompressionLevel Optimal
Remove-Item $stage -Recurse -Force

$kb = [math]::Round((Get-Item $Zip).Length / 1KB)
"Paket: $Zip  ($kb kB)"
"Prejemnik ga razsiri in v mapi pozene install.ps1 (glej ZAZENI.txt)."
