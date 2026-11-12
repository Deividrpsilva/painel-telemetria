<#
  Painel de Telemetria - instalador
  Instala o turing-smart-screen-python (open source) com o tema PainelTelemetria e os sensores extras
  (volume, FPS/frametime, SSD), e cria uma tarefa para iniciar junto com o Windows.

  Uso (o Instalar.bat já faz isso como administrador):
    instalar.ps1                    instala/reinstala tudo
    instalar.ps1 -Simulador         usa a tela simulada (http://localhost:5678) em vez da tela USB
    instalar.ps1 -SoAtualizarTema   só copia tema + sensores de novo e reinicia o painel (para ajustes)
    instalar.ps1 -SemInicioAutomatico   não cria a tarefa de inicialização
    instalar.ps1 -Instalador        chamado pelo PainelTelemetria-Setup.exe (sem pausas)
#>
param(
    [switch]$Simulador,
    [switch]$SoAtualizarTema,
    [switch]$SemInicioAutomatico,
    [switch]$Instalador,
    [string]$Destino = "C:\PainelTelemetria"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # deixa o Invoke-WebRequest muito mais rápido
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$VersaoApp   = "3.10.0"                      # versão testada do turing-smart-screen-python
$VersaoPy    = "3.12.10"
$NomeTarefa  = "PainelTelemetria"
$Pacote      = $PSScriptRoot
$App         = Join-Path $Destino "app"
$Venv        = Join-Path $App ".venv"
$PyVenv      = Join-Path $Venv "Scripts\python.exe"
$PywVenv     = Join-Path $Venv "Scripts\pythonw.exe"

function Passo($t)  { Write-Host ""; Write-Host "==> $t" -ForegroundColor Cyan }
function Ok($t)     { Write-Host "    $t" -ForegroundColor Green }
function Aviso($t)  { Write-Host "    $t" -ForegroundColor Yellow }

# ---------- 0. administrador ----------
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "Execute como administrador (use o Instalar.bat)." -ForegroundColor Red
    exit 1
}

# Arquivos extraídos de um zip baixado da internet ficam "bloqueados" (Mark of the Web) e o .NET
# se recusa a carregar a DLL do LibreHardwareMonitor. Remove o bloqueio do pacote.
Get-ChildItem -Path $PSScriptRoot -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

function Parar-Painel {
    Stop-ScheduledTask -TaskName $NomeTarefa -ErrorAction SilentlyContinue
    # o python do venv cria um processo filho (python da instalação base): encerra pelos dois caminhos
    if ((Test-Path $PyVenv) -and (Test-Path (Join-Path $App "painel\parar_painel.py"))) {
        $eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & $PyVenv (Join-Path $App "painel\parar_painel.py") 2>&1 | Out-Null
        $ErrorActionPreference = $eap
    }
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine -match '(main|iniciar|config_ui)\.py' -and
                       ($_.CommandLine -like "*$App*" -or $_.CommandLine -match 'Python3\d+\\pythonw?\.exe') } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

function Copiar-TemaESensores {
    Passo "Copiando sensores e configurador"
    Copy-Item -Force (Join-Path $Pacote "sensors_custom.py") (Join-Path $App "library\sensors\sensors_custom.py")
    Copy-Item -Force -Recurse (Join-Path $Pacote "app\painel\*") (Join-Path $App "painel")
    Ok "Sensores e configurador atualizados."
}

function Gerar-Tema {
    # (re)gera os temas do usuário (C:\PainelTelemetria\temas\*.json) em app\res\themes
    Push-Location $App
    try {
        $eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & $PyVenv "painel\gerador.py" 2>&1 | Out-Null
        $ErrorActionPreference = $eap
    } finally { Pop-Location }
    Ok "Temas personalizados gerados."
}

function Iniciar-Painel {
    if (Get-ScheduledTask -TaskName $NomeTarefa -ErrorAction SilentlyContinue) {
        Start-ScheduledTask -TaskName $NomeTarefa
    } else {
        Start-Process -FilePath $PywVenv -ArgumentList "painel\iniciar.py" -WorkingDirectory $App
    }
    Ok "Painel iniciado."
}

if ($SoAtualizarTema) {
    if (-not (Test-Path $PyVenv)) { Write-Host "Painel não instalado em $Destino. Rode a instalação completa." -ForegroundColor Red; exit 1 }
    Parar-Painel
    Copiar-TemaESensores
    Get-ChildItem -Path $Destino -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
    Gerar-Tema
    Iniciar-Painel
    exit 0
}

# ---------- 1. Python ----------
Passo "Verificando o Python"
function Achar-Python {
    # 3.10 a 3.13 (o pythonnet usado pelo LibreHardwareMonitor ainda não suporta 3.14)
    $teste = "import sys; print(sys.executable if (3,10) <= sys.version_info[:2] <= (3,13) else '')"
    $eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            foreach ($v in @("-3.12", "-3.13", "-3.11")) {
                $exe = & py $v -c $teste 2>$null
                if ($LASTEXITCODE -eq 0 -and $exe) { $exe = "$exe".Trim(); if ($exe -and (Test-Path $exe)) { return $exe } }
            }
        }
        if (Get-Command python -ErrorAction SilentlyContinue) {
            $exe = & python -c $teste 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) {
                $exe = "$exe".Trim()
                if ($exe -and (Test-Path $exe) -and ($exe -notlike "*WindowsApps*")) { return $exe }
            }
        }
    } finally { $ErrorActionPreference = $eap }
    foreach ($p in @("$env:ProgramFiles\Python312\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}
$Py = Achar-Python
if (-not $Py) {
    Aviso "Python não encontrado. Baixando Python $VersaoPy..."
    $inst = Join-Path $env:TEMP "python-$VersaoPy-amd64.exe"
    Invoke-WebRequest "https://www.python.org/ftp/python/$VersaoPy/python-$VersaoPy-amd64.exe" -OutFile $inst -UseBasicParsing
    Start-Process -Wait -FilePath $inst -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_launcher=1"
    $Py = Achar-Python
    if (-not $Py) { Write-Host "Falha ao instalar o Python." -ForegroundColor Red; exit 1 }
}
Ok "Python: $Py"

# ---------- 2. TURMO ----------
Passo "Verificando o TURMO"
$turmo = Get-Process | Where-Object { $_.ProcessName -match "TURMO|TURZX" }
if ($turmo) {
    Aviso "O TURMO está aberto e ocupa a porta da tela. Ele será fechado."
    $turmo | Stop-Process -Force
    Aviso "Lembre de desmarcar 'Startup' nas configurações do TURMO para ele não abrir com o Windows."
} else { Ok "TURMO não está rodando." }

# ---------- 3. baixar o programa ----------
Parar-Painel
Passo "Copiando turing-smart-screen-python $VersaoApp (incluído no pacote)"
$src = Get-Item (Join-Path $Pacote "app")

# preserva o config.yaml e o venv de uma instalação anterior
$cfgAntigo = $null
if (Test-Path (Join-Path $App "config.yaml")) { $cfgAntigo = Get-Content -Raw (Join-Path $App "config.yaml") }
New-Item -ItemType Directory -Force -Path $App | Out-Null
Get-ChildItem $App -Force | Where-Object { $_.Name -ne ".venv" } | Remove-Item -Recurse -Force
Copy-Item -Recurse -Force (Join-Path $src.FullName "*") $App
Copiar-TemaESensores
Get-ChildItem -Path $Destino -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
Ok "Programa em $App"

# ---------- 4. dependências ----------
Passo "Instalando dependências (pode levar alguns minutos)"
if (-not (Test-Path $PyVenv)) { & $Py -m venv $Venv }
$reqArq = Join-Path $Pacote "requirements-painel.txt"
Copy-Item -Force $reqArq (Join-Path $App "requirements-painel.txt")
$rodas = Join-Path $Pacote "wheels"      # pacotes que só existem como código-fonte, já prontos
& $PyVenv -m pip install --disable-pip-version-check -q --upgrade pip
& $PyVenv -m pip install --disable-pip-version-check --find-links $rodas -r $reqArq
if ($LASTEXITCODE -ne 0) { Write-Host "Falha ao instalar dependências." -ForegroundColor Red; exit 1 }
Ok "Dependências instaladas."
Gerar-Tema

# ---------- 5. config ----------

Passo "Configurando"
$cfgPath = Join-Path $App "config.yaml"
$cfg = Get-Content -Raw $cfgPath
# placa de rede ativa (a da rota padrão)
$rede = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
    Sort-Object { $_.RouteMetric + $_.InterfaceMetric } | Select-Object -First 1
$nomeRede = if ($rede) { $rede.InterfaceAlias } else { "" }
$revisao = if ($Simulador) { "SIMU" } else { "A" }
$cfg = $cfg -replace '(?m)^(\s*THEME:).*$', '$1 PainelTelemetria'
$cfg = $cfg -replace '(?m)^(\s*HW_SENSORS:).*$', '$1 LHM'
$cfg = $cfg -replace '(?m)^(\s*COM_PORT:).*$', '$1 "AUTO"'
$cfg = $cfg -replace '(?m)^(\s*ETH:).*$', ('$1 "' + $nomeRede + '" # placa de rede ativa (detectada pelo instalador)')
$cfg = $cfg -replace '(?m)^(\s*WLO:).*$', '$1 ""'
$cfg = $cfg -replace '(?m)^(\s*REVISION:).*$', ('$1 ' + $revisao)
if ($cfgAntigo) {  # mantém as escolhas de uma instalação anterior
    foreach ($chave in @("BRIGHTNESS", "DISPLAY_REVERSE", "THEME")) {
        if ($cfgAntigo -match "(?m)^\s*$($chave):[ \t]*([^\r\n#]+)") {
            $valor = $Matches[1].Trim()
            $cfg = $cfg -replace "(?m)^(\s*$($chave):).*$", ('$1 ' + $valor)
        }
    }
}
[IO.File]::WriteAllText($cfgPath, $cfg, (New-Object Text.UTF8Encoding $false))
Ok "Tela: revisão $revisao | Rede monitorada: '$nomeRede'"

# ---------- 6. atalhos ----------
Passo "Criando atalhos"
# versões antigas usavam .bat e um atalho "Configurar painel"
foreach ($velho in @("Editor de tema.bat", "Configuracao avancada.bat", "Configurar.bat", "Configurar painel.bat")) {
    Remove-Item -Force (Join-Path $Destino $velho) -ErrorAction SilentlyContinue
}
$mesas = @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("CommonDesktopDirectory"))
foreach ($m in $mesas) { Remove-Item -Force (Join-Path $m "Configurar painel.lnk") -ErrorAction SilentlyContinue }
$icone = Join-Path $App "painel\painel.ico"
$menu = Join-Path ([Environment]::GetFolderPath("CommonPrograms")) "Painel de Telemetria.lnk"
$mesa = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "Painel de Telemetria.lnk"
try {
    $ws = New-Object -ComObject WScript.Shell
    foreach ($arq in @($menu, $mesa)) {
        $lnk = $ws.CreateShortcut($arq)
        $lnk.TargetPath = $PywVenv
        $lnk.Arguments = '"' + (Join-Path $App "painel\abrir.py") + '"'
        $lnk.WorkingDirectory = $App
        $lnk.IconLocation = "$icone,0"
        $lnk.Description = "Configurar a tela de telemetria"
        $lnk.Save()
    }
    Ok "Atalho 'Painel de Telemetria' na Área de Trabalho e no Menu Iniciar."
} catch { Aviso "Não foi possível criar os atalhos: $_" }
# a janela de configuração pode ser aberta sem administrador: libera escrita na pasta para os usuários
$eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
& icacls $Destino /grant "*S-1-5-32-545:(OI)(CI)M" /T /Q 2>&1 | Out-Null
$ErrorActionPreference = $eap
@"
@echo off
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)
title Painel - diagnostico
cd /d "$App"
schtasks /End /TN $NomeTarefa >nul 2>&1
"$PyVenv" painel\parar_painel.py
echo Iniciando o painel com log na tela...
"$PyVenv" main.py
echo.
echo O painel parou. Tire um print desta janela e mande no chat.
pause
"@ | Set-Content -Encoding ASCII (Join-Path $Destino "Rodar com log (diagnostico).bat")
Copy-Item -Force (Join-Path $Pacote "desinstalar.ps1") $Destino

# ---------- 7. iniciar com o Windows ----------
if (-not $SemInicioAutomatico) {
    Passo "Criando tarefa para iniciar com o Windows"
    $usuario = (Get-CimInstance Win32_ComputerSystem).UserName
    if (-not $usuario) { $usuario = "$env:USERDOMAIN\$env:USERNAME" }
    $acao = New-ScheduledTaskAction -Execute $PywVenv -Argument "painel\iniciar.py" -WorkingDirectory $App
    $gatilho = New-ScheduledTaskTrigger -AtLogOn -User $usuario
    $gatilho.Delay = "PT5S"
    $principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Highest
    $config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger $gatilho -Principal $principal `
        -Settings $config -Force | Out-Null
    Ok "Tarefa '$NomeTarefa' criada para $usuario (roda como administrador, exigido pelo LibreHardwareMonitor)."
}

Passo "Iniciando o painel"
Iniciar-Painel
if ($Simulador) { Ok "Abra http://localhost:5678 no navegador para ver a tela simulada." }

Write-Host ""
Write-Host "Pronto! Pasta do painel: $Destino" -ForegroundColor Green
Write-Host " - Ícone 'Painel de Telemetria' na bandeja (perto do relógio) e na Área de Trabalho:"
Write-Host "   temas, blocos, cores, brilho e perfis Trabalho/Jogos"
Write-Host " - 'Rodar com log (diagnostico).bat': mostra erros, se algo não aparecer"
