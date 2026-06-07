#!/bin/bash
# Profile Issue Guardian Cron Wrapper
# Dijalankan setiap 6 jam (atau sesuai cron schedule)
# Tugas:
#   1. Scan master vs GitHub issues
#   2. Auto-create issue untuk profil yang belum punya
#   3. Kirim notifikasi Telegram (jika ada issue baru)
#   4. Log ke osint_archive/guardian-{date}.log
#
# Cron schedule (recommended):
#   0 */6 * * * /home/ubuntu/guardian_cron.sh
#
# Atau setiap hari jam 02:00 WIB:
#   0 2 * * * TZ=Asia/Jakarta /home/ubuntu/guardian_cron.sh

set -euo pipefail

WORKDIR="/home/ubuntu/profilasatidz"
LOGFILE="/home/ubuntu/guardian.log"
LOCKFILE="/home/ubuntu/.guardian_run_count"
TODAY=$(TZ=Asia/Jakarta date +%Y-%m-%d)
MAX_RUNS_PER_DAY=4  # 4x per hari = setiap 6 jam

cd "$WORKDIR"

log() {
    echo "[$(TZ=Asia/Jakarta date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"
}

# Rate limit: max N runs per day
COUNT=0
LAST_DATE=""
if [ -f "$LOCKFILE" ]; then
    LAST_DATE=$(head -1 "$LOCKFILE" 2>/dev/null)
    COUNT=$(tail -1 "$LOCKFILE" 2>/dev/null)
fi

if [ "$LAST_DATE" != "$TODAY" ]; then
    COUNT=0
fi

if [ "$COUNT" -ge "$MAX_RUNS_PER_DAY" ]; then
    log "Skip: already ran $COUNT times today (max $MAX_RUNS_PER_DAY)"
    exit 0
fi

# Random delay 0-15 menit (spread load + avoid thundering herd)
DELAY=$((RANDOM % 15))
log "Sleeping ${DELAY}m before run"
sleep ${DELAY}m

# Run guardian with notification
log "=== Profile Issue Guardian run start ==="
if /usr/bin/python3 "$WORKDIR/profile_issue_guardian.py" --notify 2>&1 | tee -a "$LOGFILE"; then
    log "=== Guardian run completed successfully ==="
else
    log "=== Guardian run FAILED with exit $? ==="
fi

# Update counter
COUNT=$((COUNT + 1))
echo "$TODAY" > "$LOCKFILE"
echo "$COUNT" >> "$LOCKFILE"

# Trim log file if too big (>10MB)
if [ -f "$LOGFILE" ] && [ $(stat -f%z "$LOGFILE" 2>/dev/null || stat -c%s "$LOGFILE" 2>/dev/null) -gt 10485760 ]; then
    tail -5000 "$LOGFILE" > "${LOGFILE}.tmp"
    mv "${LOGFILE}.tmp" "$LOGFILE"
    log "Log trimmed to last 5000 lines"
fi
