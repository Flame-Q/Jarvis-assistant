# Run Jarvis with the project virtual environment, no activation needed.
$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Виртуальное окружение не найдено. Создайте его: python -m venv .venv"
    exit 1
}
& $python -m jarvis @args
