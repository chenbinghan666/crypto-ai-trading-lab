#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RUNTIME="${HOME}/.local/share/crypto-ai-trading-lab"
COMMIT="1394a3f72aa4393e1a98f51b382434c4b4c2d972"
SOURCE="$RUNTIME/tradingagents-src-$COMMIT"
mkdir -p "$RUNTIME"
if [ ! -d "$SOURCE/.git" ]; then
  git init "$SOURCE"
  git -C "$SOURCE" remote add origin https://github.com/TauricResearch/TradingAgents.git
  git -C "$SOURCE" fetch --depth 1 origin "$COMMIT"
  git -C "$SOURCE" checkout --detach FETCH_HEAD
fi
test "$(git -C "$SOURCE" rev-parse HEAD)" = "$COMMIT"
python3 -m venv --without-pip "$RUNTIME/tradingagents-venv"
if ! "$RUNTIME/tradingagents-venv/bin/python" -m pip --version >/dev/null 2>&1; then
  python3 -c 'import urllib.request,sys; urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py",sys.argv[1])' "$RUNTIME/get-pip-tradingagents.py"
  "$RUNTIME/tradingagents-venv/bin/python" "$RUNTIME/get-pip-tradingagents.py"
fi
if [ -f "$ROOT/requirements-tradingagents.lock.txt" ]; then
  "$RUNTIME/tradingagents-venv/bin/python" -m pip install -r "$ROOT/requirements-tradingagents.lock.txt"
else
  "$RUNTIME/tradingagents-venv/bin/python" -m pip install "$SOURCE"
fi
"$RUNTIME/tradingagents-venv/bin/python" -m pip check
"$RUNTIME/tradingagents-venv/bin/python" -m labapp.research_probe
