# Remove o Painel de Telemetria (rode como administrador, ou use "Adicionar ou remover programas")
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
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match '(main|iniciar|config_ui)\.py' -and ($_.CommandLine -like "*$App*" -or $_.CommandLine -like "*painel\*.py*") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

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
    (Join-Path ([Environment]::GetFolderPath("CommonPrograms")) "Painel de Telemetria.lnk")
)
foreach ($a in $atalhos) { Remove-Item -Force $a -ErrorAction SilentlyContinue }
Write-Host "Painel removido. Para voltar ao TURMO, abra-o e marque 'Startup' de novo."
