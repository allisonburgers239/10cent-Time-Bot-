#!/bin/bash
# Installs the 10:00 ET weekday scan as a macOS launchd job (runs even if no terminal is open; the Mac must be awake).
set -e
cd "$(dirname "$0")/.."
mkdir -p ~/Library/LaunchAgents
cp ops/com.10c.daily-scan.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.10c.daily-scan.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.10c.daily-scan.plist
echo "installed: runs Mon-Fri 09:00 local (10:00 ET). Test now with: launchctl start com.10c.daily-scan ; then tail results/scan_log_runs.txt"
echo "remove with: launchctl unload ~/Library/LaunchAgents/com.10c.daily-scan.plist"
