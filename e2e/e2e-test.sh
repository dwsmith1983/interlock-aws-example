#!/usr/bin/env bash
set -euo pipefail

# Medallion Pipeline E2E Test Suite
# Validates the full pipeline: ingestion → interlock → Glue → Delta
#
# Prerequisites:
#   - CDK stack deployed (MedallionPipelineStack)
#   - Pipelines seeded (make seed)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
mkdir -p "$RESULTS_DIR"
LOG_FILE="$RESULTS_DIR/e2e-$(date +%Y%m%d-%H%M%S).log"

# Read stack outputs
TABLE_NAME="${TABLE_NAME:-medallion-interlock}"
REGION="${AWS_REGION:-us-east-1}"
BUCKET_NAME="${BUCKET_NAME:-}"

if [ -z "$BUCKET_NAME" ]; then
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
  BUCKET_NAME="medallion-data-${ACCOUNT_ID}"
fi

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
  echo "$msg" | tee -a "$LOG_FILE"
}

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  log "PASS: $1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  log "FAIL: $1"
}

warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  log "WARN: $1"
}

wait_for_s3_object() {
  local prefix="$1"
  local max_wait="${2:-120}"
  local elapsed=0
  while [ $elapsed -lt $max_wait ]; do
    count=$(aws s3api list-objects-v2 \
      --bucket "$BUCKET_NAME" \
      --prefix "$prefix" \
      --query "length(Contents || \`[]\`)" \
      --output text 2>/dev/null || echo "0")
    if [ "$count" != "0" ] && [ "$count" != "None" ]; then
      return 0
    fi
    sleep 10
    elapsed=$((elapsed + 10))
  done
  return 1
}

wait_for_runlog() {
  local pipeline="$1"
  local schedule="$2"
  local max_wait="${3:-300}"
  local elapsed=0
  local date_str=$(date -u +%Y-%m-%d)

  while [ $elapsed -lt $max_wait ]; do
    item=$(aws dynamodb get-item \
      --table-name "$TABLE_NAME" \
      --key "{\"PK\":{\"S\":\"PIPELINE#${pipeline}\"},\"SK\":{\"S\":\"RUNLOG#${date_str}#${schedule}\"}}" \
      --region "$REGION" 2>/dev/null || echo "")
    if [ -n "$item" ] && echo "$item" | grep -q "COMPLETED"; then
      return 0
    fi
    sleep 15
    elapsed=$((elapsed + 15))
  done
  return 1
}

# =============================================================================
# Scenario 1: Manual ingestion trigger → bronze data appears in S3
# =============================================================================
scenario_1_manual_ingestion() {
  log "--- Scenario 1: Manual ingestion trigger ---"
  local date_str=$(date -u +%Y-%m-%d)
  local hour=$(date -u +%H)

  # Trigger Wikipedia ingestion manually
  log "Invoking ingest-wikipedia Lambda..."
  aws lambda invoke \
    --function-name "${TABLE_NAME}-ingest-wikipedia" \
    --region "$REGION" \
    --payload '{}' \
    "$RESULTS_DIR/ingest-wikipedia-response.json" >/dev/null 2>&1

  local resp
  resp=$(cat "$RESULTS_DIR/ingest-wikipedia-response.json")
  if echo "$resp" | grep -q "s3_uri"; then
    pass "Wikipedia ingestion wrote data to S3"
  else
    fail "Wikipedia ingestion did not write data"
    log "Response: $resp"
  fi

  # Check S3 for bronze data
  if wait_for_s3_object "bronze/wikipedia/dt=${date_str}/hh=${hour}/" 30; then
    pass "Bronze Wikipedia data exists in S3"
  else
    fail "Bronze Wikipedia data not found in S3"
  fi
}

# =============================================================================
# Scenario 2: Dedup — second invocation should be skipped
# =============================================================================
scenario_2_dedup() {
  log "--- Scenario 2: Ingestion dedup ---"

  # Invoke GH Archive twice in quick succession
  log "First GH Archive invocation..."
  aws lambda invoke \
    --function-name "${TABLE_NAME}-ingest-gharchive" \
    --region "$REGION" \
    --payload '{}' \
    "$RESULTS_DIR/gharchive-response-1.json" >/dev/null 2>&1

  log "Second GH Archive invocation (should dedup)..."
  aws lambda invoke \
    --function-name "${TABLE_NAME}-ingest-gharchive" \
    --region "$REGION" \
    --payload '{}' \
    "$RESULTS_DIR/gharchive-response-2.json" >/dev/null 2>&1

  local resp2
  resp2=$(cat "$RESULTS_DIR/gharchive-response-2.json")
  if echo "$resp2" | grep -q "duplicate"; then
    pass "Second invocation correctly detected as duplicate"
  else
    warn "Second invocation did not report duplicate (may be different hour)"
    log "Response: $resp2"
  fi
}

# =============================================================================
# Scenario 3: Open-Meteo ingestion → bronze data
# =============================================================================
scenario_3_openmeteo() {
  log "--- Scenario 3: Open-Meteo ingestion ---"
  local date_str=$(date -u +%Y-%m-%d)
  local hour=$(date -u +%H)

  aws lambda invoke \
    --function-name "${TABLE_NAME}-ingest-openmeteo" \
    --region "$REGION" \
    --payload '{}' \
    "$RESULTS_DIR/openmeteo-response.json" >/dev/null 2>&1

  local resp
  resp=$(cat "$RESULTS_DIR/openmeteo-response.json")
  if echo "$resp" | grep -q "s3_uri"; then
    pass "Open-Meteo ingestion wrote data to S3"
  else
    fail "Open-Meteo ingestion did not write data"
    log "Response: $resp"
  fi
}

# =============================================================================
# Scenario 4: MARKER triggers Step Function execution
# =============================================================================
scenario_4_step_function() {
  log "--- Scenario 4: MARKER → Step Function execution ---"
  local date_str=$(date -u +%Y-%m-%d)
  local hour=$(date -u +%H)
  local schedule_id="h${hour}"

  # Write a test MARKER
  local ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local ttl=$(( $(date +%s) + 86400 ))
  aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --region "$REGION" \
    --item "{
      \"PK\":{\"S\":\"PIPELINE#wikipedia-silver\"},
      \"SK\":{\"S\":\"MARKER#test-e2e#${ts}\"},
      \"scheduleID\":{\"S\":\"${schedule_id}\"},
      \"timestamp\":{\"S\":\"${ts}\"},
      \"ttl\":{\"N\":\"${ttl}\"}
    }" >/dev/null 2>&1

  # Wait a moment for stream processing
  sleep 10

  # Check for Step Function execution
  local sfn_arn
  sfn_arn=$(aws cloudformation describe-stacks \
    --stack-name MedallionPipelineStack \
    --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
    --output text --region "$REGION" 2>/dev/null || echo "")

  if [ -z "$sfn_arn" ]; then
    warn "Could not find StateMachineArn from stack outputs"
    return
  fi

  local executions
  executions=$(aws stepfunctions list-executions \
    --state-machine-arn "$sfn_arn" \
    --max-results 5 \
    --region "$REGION" 2>/dev/null || echo "")

  if echo "$executions" | grep -q "wikipedia-silver"; then
    pass "Step Function execution started for wikipedia-silver"
  else
    warn "No Step Function execution found (may take longer to process)"
  fi
}

# =============================================================================
# Scenario 5: Full silver pipeline completion (if data exists)
# =============================================================================
scenario_5_silver_pipeline() {
  log "--- Scenario 5: Silver pipeline completion check ---"
  local hour=$(date -u +%H)
  local prev_hour=$(printf "%02d" $(( (10#$hour - 1 + 24) % 24 )))
  local schedule_id="h${prev_hour}"

  log "Checking if silver pipeline completed for schedule ${schedule_id}..."
  if wait_for_runlog "wikipedia-silver" "$schedule_id" 60; then
    pass "Wikipedia silver pipeline completed for ${schedule_id}"
  else
    warn "Wikipedia silver pipeline not yet completed for ${schedule_id} (expected if first run)"
  fi
}

# =============================================================================
# Scenario 6: Custom evaluator endpoint
# =============================================================================
scenario_6_evaluator() {
  log "--- Scenario 6: Custom evaluator endpoint ---"

  local api_url
  api_url=$(aws cloudformation describe-stacks \
    --stack-name MedallionPipelineStack \
    --query "Stacks[0].Outputs[?OutputKey=='EvaluatorApiUrl'].OutputValue" \
    --output text --region "$REGION" 2>/dev/null || echo "")

  if [ -z "$api_url" ]; then
    warn "Could not find EvaluatorApiUrl from stack outputs"
    return
  fi

  local resp
  resp=$(curl -s -X POST "${api_url}/evaluate/record-count" \
    -H "Content-Type: application/json" \
    -d "{\"bucket\":\"${BUCKET_NAME}\",\"prefix\":\"bronze/wikipedia/\",\"minObjects\":1}" 2>/dev/null || echo "")

  if echo "$resp" | grep -qE "PASS|FAIL"; then
    pass "Custom evaluator responded with valid status"
    log "Evaluator response: $resp"
  else
    fail "Custom evaluator returned unexpected response"
    log "Response: $resp"
  fi
}

# =============================================================================
# Run all scenarios
# =============================================================================
main() {
  log "=========================================="
  log "Medallion Pipeline E2E Test Suite"
  log "=========================================="
  log "Table:  $TABLE_NAME"
  log "Bucket: $BUCKET_NAME"
  log "Region: $REGION"
  log ""

  scenario_1_manual_ingestion
  scenario_2_dedup
  scenario_3_openmeteo
  scenario_4_step_function
  scenario_5_silver_pipeline
  scenario_6_evaluator

  log ""
  log "=========================================="
  log "Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed, ${WARN_COUNT} warnings"
  log "=========================================="
  log "Full log: $LOG_FILE"

  # Persist summary
  cat > "$RESULTS_DIR/summary.json" <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "passed": $PASS_COUNT,
  "failed": $FAIL_COUNT,
  "warnings": $WARN_COUNT,
  "log_file": "$LOG_FILE"
}
EOF

  if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
  fi
}

main "$@"
