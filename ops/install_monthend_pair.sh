#!/bin/bash
# Installs the 15:45 ET weekday month-end pair ticket as a macOS launchd job (the Mac must be awake).
set -e
cd "$(dirname "$0")/.."
mkdir -p ~/Library/LaunchAgents
cp ops/com.10c.monthend-pair.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.10c.monthend-pair.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.10c.monthend-pair.plist
echo "installed: runs Mon-Fri 14:45 local (15:45 ET). Test now with: launchctl start com.10c.monthend-pair ; then tail results/monthend_pair_runs.txt"
echo "remove with: launchctl unload ~/Library/LaunchAgents/com.10c.monthend-pair.plist"
