[CmdletBinding()]
param(
  [switch]$NoVenv
)

$ErrorActionPreference = 'Stop'

function Ensure-Elevation {
  $current = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($current)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Requesting Administrator privileges...' -ForegroundColor Yellow
    $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`"")
    try {
      Start-Process -FilePath 'powershell.exe' -ArgumentList $args -Verb RunAs | Out-Null
    } catch {
      Write-Host "Elevation failed: $($_.Exception.Message)" -ForegroundColor Red
      Read-Host 'Press Enter to close'
    }
    exit
  }
}

function Fail-AndPause([string]$message) {
  Write-Host $message -ForegroundColor Red
  Read-Host 'Press Enter to close'
  exit 1
}

try {
  Ensure-Elevation
  Set-Location -Path $PSScriptRoot

  $pyCmd = Get-Command py -ErrorAction SilentlyContinue
  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  $usePy = $false
  if ($pyCmd) { $usePy = $true }
  elseif (-not $pythonCmd) { Fail-AndPause 'Python was not found. Please install Python 3.10+ from https://www.python.org/downloads/ and re-run.' }

  if (-not $NoVenv) {
    if (-not (Test-Path '.venv')) {
      if ($usePy) { & $pyCmd.Source '-3' '-m' 'venv' '.venv' } else { & $pythonCmd.Source '-m' 'venv' '.venv' }
    }
    $pythonExe = Join-Path (Resolve-Path '.venv').Path 'Scripts/python.exe'
  } else {
    $pythonExe = if ($usePy) { $pyCmd.Source } else { $pythonCmd.Source }
  }

  & $pythonExe '-m' 'pip' 'install' '--upgrade' 'pip'
  & $pythonExe '-m' 'pip' 'install' '-r' 'requirements.txt'

  $env:MONITOR_MODE = 'local'
  $env:SAMPLE_INTERVAL_SECONDS = '1'

  Write-Host 'Starting monitor (local mode, 1s sampling) at http://localhost:8000' -ForegroundColor Green
  & $pythonExe '-m' 'app.server'
} catch {
  Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host $_.Exception.StackTrace
  Read-Host 'Press Enter to close'
}
