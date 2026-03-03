#!/usr/bin/env bash
# scripts/backfill.sh — Invoke generator for every 15-min window of a given day.
# Usage: ./scripts/backfill.sh 2026-03-03
set -euo pipefail

DATE="${1:?Usage: backfill.sh YYYY-MM-DD}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
FUNCTION_NAME="${ENVIRONMENT}-telecom-generator"
CDR_TARGET="${CDR_DAILY_TARGET:-100000000}"
SEQ_TARGET="${SEQ_DAILY_TARGET:-500000000}"

echo "Backfilling ${DATE} via ${FUNCTION_NAME}"
echo "CDR daily target: ${CDR_TARGET}, SEQ daily target: ${SEQ_TARGET}"
echo ""

for hour in $(seq -w 0 23); do
    for minute in 0 15 30 45; do
        window=$(printf "%sT%s:%02d:00+00:00" "$DATE" "$hour" "$minute")

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
        done
    done
    echo "  Hour ${hour} complete (8 invocations)"
done

echo ""
echo "Backfill complete: 192 Lambda invocations (96 windows x 2 streams)"
echo "Monitor bronze consumer logs and Interlock SFN for pipeline progress."
