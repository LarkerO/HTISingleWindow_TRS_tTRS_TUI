param(
    [switch]$Demo,
    [switch]$Ascii,
    [switch]$Keys,
    [string]$Config
)
$ErrorActionPreference = 'Stop'
$ttrsArgs = @()
if ($Demo) { $ttrsArgs += '--demo' }
if ($Ascii) { $ttrsArgs += '--ascii' }
if ($Keys) { $ttrsArgs += '--keys' }
if ($Config) { $ttrsArgs += @('--config', $Config) }
Push-Location $PSScriptRoot
try {
    if (Test-Path '.venv/Scripts/python.exe') {
        & '.venv/Scripts/python.exe' -m ttrs @ttrsArgs
    } elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv run --locked ttrs @ttrsArgs
    } else {
        # This workspace may have been prepared using the Codex bundled runtime.
        $bundled = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
        if ((Test-Path '.deps/textual') -and (Test-Path $bundled)) {
            & $bundled dev.py @ttrsArgs
        } else {
            throw '请先使用 Python 3.12+ 创建虚拟环境并 pip install -e .，或安装 uv 后 uv sync --locked。'
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "tTRS exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
