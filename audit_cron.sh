#!/bin/bash
# Audit Corruption Cron Wrapper
# Dijalankan harian jam 02:00 WIB (setelah guardian 00:00, sebelum nyicil_review 16:00)
# Tugas:
#   1. File-based static audit (Phase 1, 0 API calls) — bio + pendidikan + karya + expertise
#   2. State tracking per-agent di osint_archive/audit_state_agent_*.json
#   3. Quarantine file corrupt (Lesson #10) + delete detail
#   4. Optional: GitHub issue creation untuk kasus ambiguous
#   5. Log ke osint_archive/audit_cron-{date}.log
#
# Cron schedule (recommended):
#   0 2 * * * TZ=Asia/Jakarta /home/ubuntu/audit_cron.sh
#
# Mutual exclusion: flock di osint_archive/audit.lock (Lesson #12 prevention)
# Multi-agent: MAX_AGENTS env var, default 1 (conservative)

set -euo pipefail

WORKDIR="/home/ubuntu/profilasatidz"
LOGDIR="$WORKDIR/osint_archive"
LOCKFILE="$LOGDIR/audit.lock"
MAX_AGENTS="${AUDIT_MAX_AGENTS:-1}"  # 1 = sequential conservative
BATCH_PER_AGENT="${AUDIT_BATCH:-10}"  # 10 files per agent per run
TODAY=$(TZ=Asia/Jakarta date +%Y-%m-%d)
LOGFILE="$LOGDIR/audit_cron-${TODAY}.log"

cd "$WORKDIR"

log() {
    echo "[$(TZ=Asia/Jakarta date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOGFILE"
}

# === Mutual exclusion: flock ===
if [ ! -d "$LOGDIR" ]; then
    mkdir -p "$LOGDIR"
fi

if command -v flock >/dev/null 2>&1; then
    # Acquire non-blocking lock. If another audit_cron.sh is running, exit 0.
    exec 200>"$LOCKFILE"
    if ! flock -n 200; then
        log "Skip: another audit_cron.sh is already running (lock held)"
        exit 0
    fi
    log "Acquired flock $LOCKFILE"
else
    log "WARNING: flock not available, proceeding without mutual exclusion"
fi

# === Random delay 0-15 menit (Lesson #12 + spread load) ===
DELAY=$((RANDOM % 15))
log "Sleeping ${DELAY}m before run (random spread)"
sleep ${DELAY}m

# === Run Phase 1: file-based static audit (zero API) ===
log "=== Audit corruption run start (agents=$MAX_AGENTS batch=$BATCH_PER_AGENT) ==="

# Single-agent mode (default) — simpler, no risk
if [ "$MAX_AGENTS" -le 1 ]; then
    if /usr/bin/python3 "$WORKDIR/audit_corruption.py" \
        --detail-dir "$WORKDIR/detail" \
        --state-dir "$LOGDIR" \
        --quarantine-dir "$LOGDIR/quarantine" \
        --batch "$BATCH_PER_AGENT" \
        --agents 1 \
        --agent-id 0 \
        2>&1 | tee -a "$LOGFILE"; then
        log "=== Single-agent run completed ==="
    else
        EXIT=$?
        log "=== Single-agent run FAILED with exit $EXIT ==="
    fi
else
    # Multi-agent mode (Lesson #12: disjoint sets via partition_files)
    AGENT_PIDS=()
    for ((i=0; i<MAX_AGENTS; i++)); do
        /usr/bin/python3 "$WORKDIR/audit_corruption.py" \
            --detail-dir "$WORKDIR/detail" \
            --state-dir "$LOGDIR" \
            --quarantine-dir "$LOGDIR/quarantine" \
            --batch "$BATCH_PER_AGENT" \
            --agents "$MAX_AGENTS" \
            --agent-id "$i" \
            2>>"$LOGFILE" >>"$LOGFILE" &
        AGENT_PIDS+=($!)
    done

    # Wait for all agents
    FAILED=0
    for pid in "${AGENT_PIDS[@]}"; do
        if ! wait "$pid"; then
            FAILED=$((FAILED + 1))
            log "Agent PID $pid FAILED"
        fi
    done
    if [ "$FAILED" -eq 0 ]; then
        log "=== Multi-agent run ($MAX_AGENTS agents) completed ==="
    else
        log "=== Multi-agent run completed with $FAILED failures ==="
    fi
fi

# === Optional Phase 1.5: Create GitHub issues for ambiguous cases ===
if [ "${AUDIT_CREATE_ISSUES:-0}" = "1" ]; then
    log "=== Creating GH issues for ambiguous cases ==="
    if /usr/bin/python3 "$WORKDIR/create_audit_issues.py" \
        --state-dir "$LOGDIR" \
        2>&1 | tee -a "$LOGFILE"; then
        log "=== Issue creation completed ==="
    else
        log "=== Issue creation FAILED (non-fatal) ==="
    fi
fi

# === Trim log file if too big (>10MB) ===
if [ -f "$LOGFILE" ]; then
    SIZE=$(stat -f%z "$LOGFILE" 2>/dev/null || stat -c%s "$LOGFILE" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt 10485760 ]; then
        tail -5000 "$LOGFILE" > "${LOGFILE}.tmp"
        mv "${LOGFILE}.tmp" "$LOGFILE"
        log "Log trimmed to last 5000 lines"
    fi
fi

# Release flock (auto on exit 200)
log "=== Audit corruption run end ==="
