<#
  Gera o instalador MSI do NetTerminal.

  Pré-requisito (uma vez por máquina de build): WiX Toolset v4+ (comando "wix").
      winget install --id WiXToolset.WiXCLI
  ou, com o .NET SDK instalado:
      dotnet tool install --global wix

  Uso (na raiz do projeto):
      powershell -ExecutionPolicy Bypass -File installer\build_msi.ps1
      powershell -ExecutionPolicy Bypass -File installer\build_msi.ps1 -PularExe   # reaproveita dist\NETerminal.exe

  Saída:
      dist\NetTerminal-<versao>.msi
      dist\versao.json  -> modelo do JSON para o servidor de atualização
                           (preencha "url_download" e publique junto com o .msi)
#>
param(
    [switch]$PularExe,
    # Endereço onde o .msi será publicado (sem o nome do arquivo). Ex. no GitHub:
    # https://github.com/USUARIO/REPO/releases/download/v2.1.0
    [string]$UrlDownloadBase = "https://SEU-SERVIDOR"
)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

# Versão única: vem de netterminal/__init__.py
$versao = (Select-String -Path "netterminal\__init__.py" -Pattern 'APP_VERSION = "([\d\.]+)"').Matches[0].Groups[1].Value
Write-Host "NetTerminal versão $versao"

if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
    throw "WiX Toolset não encontrado. Instale com: winget install --id WiXToolset.WiXCLI"
}

if (-not $PularExe) {
    Write-Host "1/3 Gerando executável..."
    & .\.venv\Scripts\pyinstaller.exe NETerminal.spec --noconfirm --log-level WARN
    if ($LASTEXITCODE -ne 0) { throw "Falha no PyInstaller" }
}
if (-not (Test-Path "dist\NETerminal.exe")) { throw "dist\NETerminal.exe não existe" }

$incluirEnv = if (Test-Path ".env") { "1" } else { "0" }
if ($incluirEnv -eq "1") { Write-Host "   .env encontrado: será incluído no instalador (confira que não contém segredos)." }

Write-Host "2/3 Gerando MSI..."
$msi = "dist\NetTerminal-$versao.msi"
Push-Location installer
wix build NetTerminal.wxs -d Versao=$versao -d IncluirEnv=$incluirEnv -o "..\$msi"
$codigo = $LASTEXITCODE
Pop-Location
if ($codigo -ne 0) { throw "Falha no WiX" }

Write-Host "3/3 Calculando SHA-256..."
$hash = (Get-FileHash $msi -Algorithm SHA256).Hash.ToLower()
$json = [ordered]@{
    versao       = $versao
    url_download = "$($UrlDownloadBase.TrimEnd('/'))/NetTerminal-$versao.msi"
    sha256       = $hash
    obrigatoria  = $false
    notas        = ""
} | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $raiz "dist\versao.json"), $json, (New-Object Text.UTF8Encoding $false))

Write-Host ""
Write-Host "Pronto:"
Write-Host "  $msi"
Write-Host "  SHA-256: $hash"
Write-Host "  dist\versao.json (ajuste url_download antes de publicar)"
Write-Host ""
Write-Host "Instalação silenciosa (ex.: GPO/Intune):  msiexec /i $msi /qn"
Write-Host "Sem atalho na área de trabalho:           msiexec /i $msi /qn ATALHO_DESKTOP=0"
