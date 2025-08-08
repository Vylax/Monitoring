@echo off
setlocal

set SCRIPT_DIR=%~dp0
set PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe

:: Check admin
%PS% -NoProfile -Command "if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 1 }"
if %ERRORLEVEL% NEQ 0 (
  echo Requesting Administrator privileges...
  %PS% -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','""%SCRIPT_DIR%run_local_admin.ps1""'"
  goto :eof
)

%PS% -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_local_admin.ps1"
if %ERRORLEVEL% NEQ 0 (
  echo Script exited with error code %ERRORLEVEL%
  pause
)
endlocal
