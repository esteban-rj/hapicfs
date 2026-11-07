param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv --without-pip .venv
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno virtual.' }
}
& $taskPython -c 'import fastapi, uvicorn, mcp, docker, cryptography' 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m pip --python .venv install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias Python.' }
}
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) {
    $taskPnpm = Get-Command pnpm -ErrorAction SilentlyContinue
    if (-not $taskPnpm) { throw 'Compila la interfaz con pnpm install y pnpm build en frontend. Se requiere Node 24 y pnpm 11.' }
    Push-Location frontend
    try {
        pnpm --ignore-workspace install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias de la interfaz.' }
        pnpm --ignore-workspace build
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar la interfaz.' }
    } finally { Pop-Location }
}
Write-Host "Hapic: http://127.0.0.1:$Port"
if (Test-Path -LiteralPath '.env') {
    & $taskPython -m uvicorn backend.app:app --host 127.0.0.1 --port $Port --env-file .env
} else {
    & $taskPython -m uvicorn backend.app:app --host 127.0.0.1 --port $Port
}
