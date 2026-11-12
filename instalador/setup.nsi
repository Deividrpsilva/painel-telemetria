; PULSE — System Telemetry - instalador (NSIS)
; Gera PULSE-Setup.exe: copia o programa, roda o instalar.ps1 (Python, dependências, temas, tarefa que
; inicia com o Windows, atalhos) e registra em "Adicionar ou remover programas".
; A pasta (C:\PainelTelemetria), a tarefa e a chave do registro mantêm os nomes da versão 6, para que a
; atualização preserve temas e configurações e não crie uma segunda instalação.
Unicode true
SetCompressor /SOLID lzma
ManifestDPIAware true

!include "MUI2.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"

!define NOME "PULSE — System Telemetry"
!define VERSAO "7.0"
!define AUTOR "Deivid Robinson"
!define SITE "https://github.com/Deividrpsilva/painel-telemetria"
!define CHAVE "Software\Microsoft\Windows\CurrentVersion\Uninstall\PainelTelemetria"
!define PS '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass'

Name "${NOME}"
OutFile "PULSE-Setup.exe"
InstallDir "C:\PainelTelemetria"
RequestExecutionLevel admin
BrandingText "${NOME} ${VERSAO}"
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "7.0.0.0"
VIAddVersionKey /LANG=1046 "ProductName" "${NOME}"
VIAddVersionKey /LANG=1046 "FileDescription" "Instalador do ${NOME}"
VIAddVersionKey /LANG=1046 "FileVersion" "${VERSAO}"
VIAddVersionKey /LANG=1046 "ProductVersion" "${VERSAO}"
VIAddVersionKey /LANG=1046 "CompanyName" "${AUTOR}"
VIAddVersionKey /LANG=1046 "LegalCopyright" "${AUTOR} - GPL-3.0 (inclui turing-smart-screen-python)"

!define MUI_ICON "pacote\app\painel\pulse.ico"
!define MUI_UNICON "pacote\app\painel\pulse.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "pulse_instalador_lateral.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "pulse_instalador_cabecalho.bmp"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Instalar o ${NOME}"
!define MUI_WELCOMEPAGE_TEXT "Monitoramento e telemetria de hardware em tempo real na tela USB de 3,5$\" (Turing Smart Screen), no lugar do TURMO.$\r$\n$\r$\n\
- A tela começa a mostrar a telemetria assim que você entra no Windows.$\r$\n\
- O ícone do PULSE fica na bandeja, perto do relógio (em $\"mostrar ícones ocultos$\"), para abrir a configuração, trocar o perfil Trabalho/Jogos e o brilho.$\r$\n\
- Se já houver uma versão instalada, ela é atualizada e seus temas e configurações são mantidos.$\r$\n$\r$\n\
A instalação precisa de internet para baixar os componentes do Python (cerca de 60 MB) e leva alguns minutos.$\r$\n$\r$\n\
Se o TURMO estiver aberto, ele será fechado."
!define MUI_FINISHPAGE_TITLE "${NOME} instalado"
!define MUI_FINISHPAGE_TEXT "A tela já está sendo atualizada.$\r$\n$\r$\n\
Para configurar depois: clique no ícone do PULSE perto do relógio (setinha ^ da bandeja) ou no atalho $\"PULSE$\" da Área de Trabalho.$\r$\n$\r$\n\
Desmarque $\"Startup$\" no TURMO para ele não abrir mais com o Windows."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o PULSE agora"
!define MUI_FINISHPAGE_RUN_FUNCTION AbrirPainel

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "O ${NOME} precisa do Windows 64 bits."
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd

Function un.onInit
  SetRegView 64
FunctionEnd

Section "Instalar"
  ${DisableX64FSRedirection}          ; usa o PowerShell de 64 bits
  InitPluginsDir
  DetailPrint "Extraindo arquivos..."
  SetDetailsPrint listonly
  SetOutPath "$PLUGINSDIR\pacote"
  File /r "pacote\*"
  SetDetailsPrint both
  DetailPrint "Instalando em $INSTDIR (pode levar alguns minutos)..."
  nsExec::ExecToLog '${PS} -File "$PLUGINSDIR\pacote\instalar.ps1" -Destino "$INSTDIR" -Instalador'
  Pop $0
  ${If} $0 != 0
    DetailPrint "A instalação falhou (código $0)."
    MessageBox MB_ICONSTOP "A instalação não terminou (código $0).$\r$\n$\r$\nClique em $\"Mostrar detalhes$\", tire um print das últimas linhas e mande no chat."
    SetOutPath "$TEMP"
    Abort
  ${EndIf}

  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"
  WriteRegStr HKLM "${CHAVE}" "DisplayName" "${NOME}"
  WriteRegStr HKLM "${CHAVE}" "DisplayVersion" "${VERSAO}"
  WriteRegStr HKLM "${CHAVE}" "Publisher" "${AUTOR}"
  WriteRegStr HKLM "${CHAVE}" "DisplayIcon" "$INSTDIR\app\painel\pulse.ico"
  WriteRegStr HKLM "${CHAVE}" "URLInfoAbout" "${SITE}"
  WriteRegStr HKLM "${CHAVE}" "HelpLink" "${SITE}"
  WriteRegStr HKLM "${CHAVE}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${CHAVE}" "UninstallString" '"$INSTDIR\Desinstalar.exe"'
  WriteRegDWORD HKLM "${CHAVE}" "NoModify" 1
  WriteRegDWORD HKLM "${CHAVE}" "NoRepair" 1
  WriteRegDWORD HKLM "${CHAVE}" "EstimatedSize" 250000
  SetOutPath "$TEMP"                  ; libera a pasta temporária
SectionEnd

Function AbrirPainel
  ${DisableX64FSRedirection}
  SetOutPath "$INSTDIR\app"
  Exec '"$INSTDIR\app\.venv\Scripts\pythonw.exe" "$INSTDIR\app\painel\abrir.py"'
  SetOutPath "$TEMP"
FunctionEnd

Section "Uninstall"
  ${DisableX64FSRedirection}
  StrCpy $1 ""
  MessageBox MB_YESNO|MB_ICONQUESTION "Manter seus temas para uma futura instalação?$\r$\n$\r$\n(Sim: ficam em $INSTDIR\temas.  Não: apaga tudo.)" IDNO apagar
  StrCpy $1 "-ManterTemas"
  apagar:
  ${If} ${FileExists} "$INSTDIR\desinstalar.ps1"
    CopyFiles /SILENT "$INSTDIR\desinstalar.ps1" "$TEMP\painel-desinstalar.ps1"
    nsExec::ExecToLog '${PS} -File "$TEMP\painel-desinstalar.ps1" -Destino "$INSTDIR" $1'
    Pop $0
    Delete "$TEMP\painel-desinstalar.ps1"
  ${EndIf}
  Delete "$INSTDIR\Desinstalar.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "${CHAVE}"
SectionEnd
