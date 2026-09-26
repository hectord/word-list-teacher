#!/usr/bin/env bash
#
# Run the WLT server with the database stored in ./data
#
# Usage:
#   ./run.sh                  # serve on 127.0.0.1:8000
#   HOST=0.0.0.0 PORT=9000 ./run.sh
#   RELOAD=1 ./run.sh         # auto-reload on code changes
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="${ROOT}/app"
DATA="${ROOT}/data"

# Prefer the project virtualenv if present, otherwise use system python.
if [ -x "${ROOT}/myenv/bin/python" ]; then
    PYTHON="${ROOT}/myenv/bin/python"
else
    PYTHON="python3"
fi

EXTRA_ARGS=()
if [ "${RELOAD:-}" = "1" ]; then
    EXTRA_ARGS+=(--reload)
fi

cd "${APP}"
export DATADIR="${DATA}"

exec "${PYTHON}" -m uvicorn server:app \
    --host "${HOST:-127.0.0.1}" \
    --port "${PORT:-8000}" \
    "${EXTRA_ARGS[@]}"