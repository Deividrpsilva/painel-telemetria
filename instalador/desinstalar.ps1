# Remove o PULSE — System Telemetry (rode como administrador, ou use "Adicionar ou remover programas")
#   desinstalar.ps1               remove tudo
#   desinstalar.ps1 -ManterTemas  mantém seus temas (pasta temas), imagens de fundo e perfis
param([string]$Destino = "C:\PainelTelemetria", [switch]$ManterTemas)
$App = Join-Path $Destino "app"
Stop-ScheduledTask -TaskName PainelTelemetria -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName PainelTelemetria -Confirm:$false -ErrorAction SilentlyContinue
$parar = Join-Path $App "painel\parar_painel.py"
$py = Join-Path $App ".venv\Scripts\python.exe"
if ((Test-Path $py) -and (Test-Path $parar)) {
    $eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $py $parar 2>&1 | Out-Null
    $ErrorActionPreference = $eap
}
# encerra e espera fechar: python do PULSE pela linha de comando e qualquer processo rodando da pasta
# ou com uma DLL dela carregada (o main.py prende as DLLs do LibreHardwareMonitor)
for ($i = 0; $i -lt 10; $i++) {
    $ids = @()
    $ids += Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match '(main|iniciar|config_ui|splash|abrir)\.py' -and ($_.CommandLine -like "*$App*" -or $_.CommandLine -like "*painel\*.py*" -or $_.CommandLine -match 'Python3\d+\\pythonw?\.exe') } |
        ForEach-Object { [int]$_.ProcessId }
    foreach ($p in Get-Process -ErrorAction SilentlyContinue) {
        if ($p.Id -eq $PID) { continue }
        try {
            if (($p.Path -and $p.Path -like "$Destino\*") -or ($p.Modules | Where-Object { $_.FileName -like "$Destino\*" })) { $ids += $p.Id }
        } catch { }
    }
    $ids = @($ids | Where-Object { $_ -ne $PID } | Sort-Object -Unique)
    if ($ids.Count -eq 0) { break }
    foreach ($id in $ids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

if ($ManterTemas) {
    $manter = @("temas", "fundos", "perfis.json")
    Get-ChildItem $Destino -Force -ErrorAction SilentlyContinue | Where-Object { $manter -notcontains $_.Name } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Seus temas ficaram em $Destino\temas."
} else {
    Remove-Item -Recurse -Force $Destino -ErrorAction SilentlyContinue
}

$atalhos = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Configurar painel.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Painel de Telemetria.lnk"),
    (Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "Painel de Telemetria.lnk"),
    (Join-Path ([Environment]::GetFolderPath("CommonPrograms")) "Painel de Telemetria.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "PULSE.lnk"),
    (Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "PULSE.lnk"),
    (Join-Path ([Environment]::GetFolderPath("CommonPrograms")) "PULSE.lnk")
)
foreach ($a in $atalhos) { Remove-Item -Force $a -ErrorAction SilentlyContinue }
Write-Host "PULSE removido. Para voltar ao TURMO, abra-o e marque 'Startup' de novo."
