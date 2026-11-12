@echo off
:: Copia tema e sensores deste pacote para C:\PainelTelemetria e reinicia o painel
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" -SoAtualizarTema
pause
