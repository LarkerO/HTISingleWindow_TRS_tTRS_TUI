#!/bin/sh
# Prefer a prepared local environment. No system files or shell profiles are changed.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ -x .local/venv-linux/bin/python ]; then
    exec .local/venv-linux/bin/python -m ttrs "$@"
elif [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m ttrs "$@"
elif command -v uv >/dev/null 2>&1; then
    exec uv run --locked ttrs "$@"
else
    printf '%s\n' '请先安装 Python 3.12+ 并执行 python3 -m venv .venv && .venv/bin/pip install -e .'
    printf '%s\n' '或安装 uv 后执行 uv sync --locked。详见 README.md。'
    exit 1
fi
