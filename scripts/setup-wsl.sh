#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="${HOME}/.local/share/crypto-ai-trading-lab"
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python >=3.11 required"'
mkdir -p "$RUNTIME"
python3 -m venv --without-pip "$RUNTIME/venv"
if ! "$RUNTIME/venv/bin/python" -m pip --version >/dev/null 2>&1; then
  python3 -c 'import urllib.request,sys; urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py",sys.argv[1])' "$RUNTIME/get-pip.py"
  "$RUNTIME/venv/bin/python" "$RUNTIME/get-pip.py"
fi
"$RUNTIME/venv/bin/python" -m pip install --only-binary=:all: --no-binary=sdnotify -r "$ROOT/requirements.lock.txt"
"$RUNTIME/venv/bin/python" -m pip install --only-binary=:all: -c "$ROOT/requirements.lock.txt" -r "$ROOT/requirements-freqai-cpu.lock.txt"
"$RUNTIME/venv/bin/freqtrade" install-ui --ui-version 3.1.3
"$RUNTIME/venv/bin/python" -m pip check
bash "$ROOT/scripts/setup-tradingagents.sh"
