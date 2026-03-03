#!/usr/bin/env bash
# scripts/backfill.sh — Invoke generator for every 15-min window from a start
# date up to the current time.
# Usage: ./scripts/backfill.sh 2026-03-03
set -euo pipefail

DATE="${1:?Usage: backfill.sh YYYY-MM-DD}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
FUNCTION_NAME="${ENVIRONMENT}-telecom-generator"
CDR_TARGET="${CDR_DAILY_TARGET:-100000000}"
SEQ_TARGET="${SEQ_DAILY_TARGET:-500000000}"

NOW_EPOCH=$(date -u +%s)
COUNT=0

echo "Backfilling ${DATE} up to now via ${FUNCTION_NAME}"
echo "CDR daily target: ${CDR_TARGET}, SEQ daily target: ${SEQ_TARGET}"
echo ""

for hour in $(seq -w 0 23); do
    hour_had_windows=false
    for minute in 0 15 30 45; do
        window=$(printf "%sT%s:%02d:00+00:00" "$DATE" "$hour" "$minute")
        window_no_tz=$(printf "%sT%s:%02d:00" "$DATE" "$hour" "$minute")
        window_epoch=$(date -u -jf "%Y-%m-%dT%H:%M:%S" "${window_no_tz}" +%s 2>/dev/null \
            || date -u -d "${window}" +%s 2>/dev/null)

        if [ "$window_epoch" -gt "$NOW_EPOCH" ]; then
            echo "Reached current time, stopping."
            echo ""
            echo "Backfill complete: ${COUNT} Lambda invocations"
            exit 0
        fi

        hour_had_windows=true
        for stream in cdr seq; do
            if [ "$stream" = "cdr" ]; then
                target=$CDR_TARGET
            else
                target=$SEQ_TARGET
            fi

            echo -n "${window} ${stream}... "
            aws lambda invoke \
                --function-name "$FUNCTION_NAME" \
                --cli-binary-format raw-in-base64-out \
                --payload "{\"stream\":\"${stream}\",\"daily_target\":${target},\"window_start\":\"${window}\"}" \
                --query 'StatusCode' \
                --output text \
                /dev/null 2>/dev/null
            echo "ok"
            COUNT=$((COUNT + 1))
        done
    done
    if [ "$hour_had_windows" = true ]; then
        echo "  Hour ${hour} complete"
    fi
done

echo ""
echo "Backfill complete: ${COUNT} Lambda invocations"
