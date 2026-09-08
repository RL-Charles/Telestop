#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Teleblock — Call Report
# Usage: ./scripts/call_report.sh [--today] [--blocked] [--all]
#
#   (no args)   full report
#   --today     only show today's calls
#   --blocked   only show blocked numbers section
#   --all       full report (same as no args)
# ─────────────────────────────────────────────────────────

DB=/var/lib/teleblock/calls.db
BOLD='\033[1m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
RESET='\033[0m'

# ── helpers ────────────────────────────────────────────────

q() { sudo sqlite3 "$DB" "$1"; }

header() {
    echo ""
    echo -e "${CYAN}${BOLD}══════════════════════════════════════════════════════${RESET}"
    echo -e "${CYAN}${BOLD}  $1${RESET}"
    echo -e "${CYAN}${BOLD}══════════════════════════════════════════════════════${RESET}"
}

subheader() {
    echo ""
    echo -e "${BOLD}── $1 $( printf '─%.0s' $(seq 1 $((46 - ${#1}))) )${RESET}"
}

no_data() {
    echo -e "  ${DIM}(no data)${RESET}"
}

# ── overall summary ────────────────────────────────────────

show_summary() {
    header "TELEBLOCK CALL SUMMARY"

    local total passed failed timed_out blocked unique_blocked trusted
    total=$(q "SELECT COUNT(*) FROM calls;")
    passed=$(q "SELECT COUNT(*) FROM calls WHERE result='PASS';")
    failed=$(q "SELECT COUNT(*) FROM calls WHERE result='FAIL';")
    timed_out=$(q "SELECT COUNT(*) FROM calls WHERE result='TIMEOUT';")
    blocked=$((failed + timed_out))
    unique_blocked=$(q "SELECT COUNT(DISTINCT cid) FROM calls WHERE result IN ('FAIL','TIMEOUT');")
    trusted=$(q "SELECT COUNT(*) FROM trusted_callers;")
    first_call=$(q "SELECT MIN(ts) FROM calls;")
    last_call=$(q "SELECT MAX(ts) FROM calls;")

    echo ""
    printf "  %-28s %s\n" "Total calls logged:"         "$total"
    printf "  %-28s ${GREEN}%s${RESET}\n" "Calls passed (connected):"   "$passed"
    printf "  %-28s ${RED}%s${RESET}\n"   "Calls blocked (total):"      "$blocked"
    printf "  %-28s ${YELLOW}%s${RESET}\n" "  ↳ Timed out (no digit):"  "$timed_out"
    printf "  %-28s ${YELLOW}%s${RESET}\n" "  ↳ Failed (wrong digit):"  "$failed"
    printf "  %-28s %s\n" "Unique numbers blocked:"     "$unique_blocked"
    printf "  %-28s ${GREEN}%s${RESET}\n" "Trusted callers on file:"    "$trusted"
    echo ""
    printf "  %-28s %s\n" "First call recorded:"  "$first_call"
    printf "  %-28s %s\n" "Most recent call:"     "$last_call"
}

# ── blocked numbers table ──────────────────────────────────

show_blocked() {
    subheader "BLOCKED NUMBERS"

    local where="${1:-}"

    local rows
    rows=$(q "
        SELECT cid,
               COUNT(*)              AS total,
               SUM(result='TIMEOUT') AS timed_out,
               SUM(result='FAIL')    AS failed,
               MIN(ts)               AS first_seen,
               MAX(ts)               AS last_seen
        FROM calls
        WHERE result IN ('TIMEOUT','FAIL') ${where}
        GROUP BY cid
        ORDER BY total DESC;")

    if [[ -z "$rows" ]]; then
        no_data; return
    fi

    printf "\n  ${BOLD}%-15s %7s %10s %8s  %-19s %-19s${RESET}\n" \
        "NUMBER" "BLOCKED" "TIMED-OUT" "FAILED" "FIRST SEEN" "LAST SEEN"
    printf "  %-15s %7s %10s %8s  %-19s %-19s\n" \
        "───────────────" "───────" "─────────" "──────" "───────────────────" "───────────────────"

    while IFS='|' read -r cid total timed_out failed first_seen last_seen; do
        if   [[ "$total" -ge 5 ]]; then color="$RED"
        elif [[ "$total" -ge 2 ]]; then color="$YELLOW"
        else                             color="$RESET"
        fi
        printf "  ${color}%-15s %7s %10s %8s${RESET}  ${DIM}%-19s %-19s${RESET}\n" \
            "$cid" "$total" "$timed_out" "$failed" "$first_seen" "$last_seen"
    done <<< "$rows"

    local total_blocked unique
    total_blocked=$(q "SELECT COUNT(*) FROM calls WHERE result IN ('TIMEOUT','FAIL') ${where};")
    unique=$(q "SELECT COUNT(DISTINCT cid) FROM calls WHERE result IN ('TIMEOUT','FAIL') ${where};")
    echo ""
    echo -e "  ${DIM}$total_blocked blocked calls from $unique unique numbers${RESET}"
}

# ── all numbers full breakdown ─────────────────────────────

show_all_numbers() {
    subheader "ALL NUMBERS — FULL BREAKDOWN"

    local rows
    rows=$(q "
        SELECT cid,
               COUNT(*)              AS total,
               SUM(result='PASS')    AS passed,
               SUM(result='TIMEOUT') AS timed_out,
               SUM(result='FAIL')    AS failed,
               MAX(ts)               AS last_call
        FROM calls
        GROUP BY cid
        ORDER BY total DESC;")

    if [[ -z "$rows" ]]; then
        no_data; return
    fi

    printf "\n  ${BOLD}%-15s %6s %7s %10s %8s  %-19s${RESET}\n" \
        "NUMBER" "TOTAL" "PASSED" "TIMED-OUT" "FAILED" "LAST CALL"
    printf "  %-15s %6s %7s %10s %8s  %-19s\n" \
        "───────────────" "──────" "──────" "─────────" "──────" "───────────────────"

    while IFS='|' read -r cid total passed timed_out failed last_call; do
        if   [[ "$passed" -gt 0 && "$timed_out" -eq 0 && "$failed" -eq 0 ]]; then
            color="$GREEN"
        elif [[ "$passed" -eq 0 ]]; then
            color="$RED"
        else
            color="$YELLOW"
        fi
        printf "  ${color}%-15s %6s %7s %10s %8s${RESET}  ${DIM}%-19s${RESET}\n" \
            "$cid" "$total" "$passed" "$timed_out" "$failed" "$last_call"
    done <<< "$rows"
}

# ── daily breakdown ────────────────────────────────────────

show_daily() {
    subheader "CALLS BY DAY (last 30 days)"

    local rows
    rows=$(q "
        SELECT DATE(ts)               AS day,
               COUNT(*)               AS total,
               SUM(result='PASS')     AS passed,
               SUM(result='TIMEOUT')  AS timed_out,
               SUM(result='FAIL')     AS failed
        FROM calls
        WHERE ts >= DATE('now','-30 days')
        GROUP BY day
        ORDER BY day DESC;")

    if [[ -z "$rows" ]]; then
        no_data; return
    fi

    printf "\n  ${BOLD}%-12s %6s %7s %10s %8s${RESET}\n" \
        "DATE" "TOTAL" "PASSED" "TIMED-OUT" "FAILED"
    printf "  %-12s %6s %7s %10s %8s\n" \
        "────────────" "──────" "──────" "─────────" "──────"

    while IFS='|' read -r day total passed timed_out failed; do
        printf "  %-12s %6s  ${GREEN}%6s${RESET}  ${YELLOW}%9s${RESET}  ${RED}%7s${RESET}\n" \
            "$day" "$total" "$passed" "$timed_out" "$failed"
    done <<< "$rows"
}

# ── trusted callers ────────────────────────────────────────

show_trusted() {
    subheader "TRUSTED CALLERS (skip challenge)"

    local rows
    rows=$(q "
        SELECT cid, call_count, first_passed_at
        FROM trusted_callers
        ORDER BY call_count DESC;")

    if [[ -z "$rows" ]]; then
        no_data; return
    fi

    printf "\n  ${BOLD}%-15s %12s  %-19s${RESET}\n" \
        "NUMBER" "TIMES PASSED" "FIRST PASSED"
    printf "  %-15s %12s  %-19s\n" \
        "───────────────" "────────────" "───────────────────"

    while IFS='|' read -r cid count first; do
        printf "  ${GREEN}%-15s %12s${RESET}  ${DIM}%-19s${RESET}\n" "$cid" "$count" "$first"
    done <<< "$rows"
}

# ── today filter ───────────────────────────────────────────

show_today() {
    local today
    today=$(date +%F)
    header "TODAY'S CALLS — $today"

    local rows
    rows=$(q "
        SELECT ts, cid, result
        FROM calls
        WHERE DATE(ts) = '$today'
        ORDER BY ts DESC;")

    if [[ -z "$rows" ]]; then
        echo ""
        echo -e "  ${DIM}No calls recorded today yet.${RESET}"
        return
    fi

    printf "\n  ${BOLD}%-21s %-15s %s${RESET}\n" "TIME" "NUMBER" "RESULT"
    printf "  %-21s %-15s %s\n" "─────────────────────" "───────────────" "──────────"

    while IFS='|' read -r ts cid result; do
        case "$result" in
            PASS)    color="$GREEN"  ;;
            FAIL)    color="$RED"    ;;
            TIMEOUT) color="$YELLOW" ;;
            *)       color="$RESET"  ;;
        esac
        printf "  ${DIM}%-21s${RESET} %-15s ${color}%s${RESET}\n" "$ts" "$cid" "$result"
    done <<< "$rows"

    local total passed blocked
    total=$(q "SELECT COUNT(*) FROM calls WHERE DATE(ts)='$today';")
    passed=$(q "SELECT COUNT(*) FROM calls WHERE DATE(ts)='$today' AND result='PASS';")
    blocked=$(q "SELECT COUNT(*) FROM calls WHERE DATE(ts)='$today' AND result IN ('FAIL','TIMEOUT');")
    echo ""
    echo -e "  ${DIM}$total calls today — ${GREEN}$passed passed${RESET}${DIM}, ${RED}$blocked blocked${RESET}"
}

# ── main ───────────────────────────────────────────────────

MODE="${1:-}"

case "$MODE" in
    --today)
        show_today
        ;;
    --blocked)
        header "BLOCKED NUMBERS REPORT"
        show_blocked
        ;;
    --all|"")
        show_summary
        show_blocked
        show_trusted
        show_daily
        show_all_numbers
        ;;
    *)
        echo "Usage: $0 [--today | --blocked | --all]"
        exit 1
        ;;
esac

echo ""
