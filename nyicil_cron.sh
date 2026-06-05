#!/bin/bash
# Wrapper: run nyicil enrichment 2x per day at random hours
# Called by cron every hour, max 2 runs per day

LOCKFILE="/home/ubuntu/.nyicil_run_count"
TODAY=$(TZ=Asia/Jakarta date +%Y-%m-%d)

# Read current count
COUNT=0
LAST_DATE=""
if [ -f "$LOCKFILE" ]; then
    LAST_DATE=$(head -1 "$LOCKFILE" 2>/dev/null)
    COUNT=$(tail -1 "$LOCKFILE" 2>/dev/null)
fi

# Reset counter if new day
if [ "$LAST_DATE" != "$TODAY" ]; then
    COUNT=0
fi

# Check if already ran 2x today
if [ "$COUNT" -ge 2 ]; then
    exit 0
fi

# Random delay: 0-30 minutes (spread load)
DELAY=$((RANDOM % 30))
sleep ${DELAY}m

# Run enrichment
/usr/bin/python3 /home/ubuntu/nyicil_enrich.py >> /home/ubuntu/nyicil.log 2>&1

# Increment counter
COUNT=$((COUNT + 1))
echo "$TODAY" > "$LOCKFILE"
echo "$COUNT" >> "$LOCKFILE"
