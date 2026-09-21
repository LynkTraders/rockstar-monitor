#!/bin/bash
# Draait de monitor op de Mac, elke minuut via launchd.
#
# De state wordt gedeeld met GitHub Actions via de repo: eerst pullen, en
# alleen pushen als er echt iets veranderd is. Zo krijg je nooit twee
# appjes voor hetzelfde bericht, ongeacht welke van de twee hem als eerste zag.
set -uo pipefail

REPO="$HOME/Developer/rockstar-monitor"
ENV_FILE="$HOME/.config/rockstar-monitor/env"
LOG="$HOME/Library/Logs/rockstar-monitor.log"

cd "$REPO" || exit 1

if [ ! -f "$ENV_FILE" ]; then
  echo "[$(date '+%F %T')] GEEN $ENV_FILE - vul je CallMeBot-gegevens in" >> "$LOG"
  exit 1
fi
set -a; . "$ENV_FILE"; set +a

# Trage bronnen niet elke minuut lastigvallen.
export SLOW_EVERY="${SLOW_EVERY:-5}"
export X_EVERY="${X_EVERY:-3}"

git pull --rebase --autostash -q 2>/dev/null

.venv/bin/python rockstar_monitor.py >> "$LOG" 2>&1
rc=$?

if ! git diff --quiet monitor_state.json 2>/dev/null; then
  git add monitor_state.json
  git commit -q -m "chore: state bijgewerkt (mac) [skip ci]"
  for _ in 1 2 3; do
    git pull --rebase --autostash -q && git push -q && break
    sleep 3
  done
fi

# Log niet laten doorgroeien.
if [ "$(wc -l < "$LOG")" -gt 5000 ]; then
  tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

exit $rc
