#!/usr/bin/env bash
set -euo pipefail

# Medallion Pipeline E2E Test Suite
# Validates the full pipeline: ingestion → interlock → Glue → Delta
#
# Prerequisites:
#   - Terraform stack deployed
#   - Pipelines seeded (make seed)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
mkdir -p "$RESULTS_DIR"
LOG_FILE="$RESULTS_DIR/e2e-$(date +%Y%m%d-%H%M%S).log"

# Read stack outputs
TABLE_NAME="${TABLE_NAME:-medallion-interlock}"
REGION="${AWS_REGION:-ap-southeast-1}"
BUCKET_NAME="${BUCKET_NAME:-}"

if [ -z "$BUCKET_NAME" ]; then
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
  BUCKET_NAME="${TABLE_NAME}-data-${ACCOUNT_ID}"
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
  local date_str=$(date -u +%Y%m%d)

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
# Scenario 1: Earthquake ingestion → bronze data appears in S3
# =============================================================================
scenario_1_earthquake_ingestion() {
  log "--- Scenario 1: Earthquake ingestion ---"
  local date_str=$(date -u +%Y%m%d)
  local hour=$(date -u +%H)

  log "Invoking ingest-earthquake Lambda..."
  aws lambda invoke \
    --function-name "${TABLE_NAME}-ingest-earthquake" \
    --region "$REGION" \
    --payload '{}' \
    "$RESULTS_DIR/earthquake-response.json" >/dev/null 2>&1

  local resp
  resp=$(cat "$RESULTS_DIR/earthquake-response.json")
  if echo "$resp" | grep -q "eventCount"; then
    pass "Earthquake ingestion completed"
    log "Response: $resp"
  else
    fail "Earthquake ingestion did not return expected response"
    log "Response: $resp"
  fi

  # Check S3 for bronze data
  if wait_for_s3_object "bronze/earthquake/par_day=${date_str}/par_hour=${hour}/" 30; then
    pass "Bronze earthquake data exists in S3"
  else
    fail "Bronze earthquake data not found in S3"
  fi
}

# =============================================================================
# Scenario 2: Crypto ingestion → bronze data appears in S3
# =============================================================================
scenario_2_crypto_ingestion() {
  log "--- Scenario 2: Crypto ingestion ---"
  local date_str=$(date -u +%Y%m%d)
  local hour=$(date -u +%H)

  log "Invoking ingest-crypto Lambda..."
  aws lambda invoke \
    --function-name "${TABLE_NAME}-ingest-crypto" \
    --region "$REGION" \
    --payload '{}' \
    "$RESULTS_DIR/crypto-response.json" >/dev/null 2>&1

  local resp
  resp=$(cat "$RESULTS_DIR/crypto-response.json")
  if echo "$resp" | grep -q "tickerCount"; then
    pass "Crypto ingestion completed"
    log "Response: $resp"
  else
    fail "Crypto ingestion did not return expected response"
    log "Response: $resp"
  fi

  # Check S3 for bronze data
  if wait_for_s3_object "bronze/crypto/par_day=${date_str}/par_hour=${hour}/" 30; then
    pass "Bronze crypto data exists in S3"
  else
    fail "Bronze crypto data not found in S3"
  fi
}

# =============================================================================
# Scenario 3: Dedup — second invocation should be skipped
# =============================================================================
scenario_3_dedup() {
  log "--- Scenario 3: Ingestion dedup ---"

  log "Second crypto invocation (should dedup)..."
  aws lambda invoke \
    --function-name "${TABLE_NAME}-ingest-crypto" \
    --region "$REGION" \
    --payload '{}' \
    "$RESULTS_DIR/crypto-response-2.json" >/dev/null 2>&1

  local resp2
  resp2=$(cat "$RESULTS_DIR/crypto-response-2.json")
  if echo "$resp2" | grep -q "duplicate"; then
    pass "Second invocation correctly detected as duplicate"
  else
    warn "Second invocation did not report duplicate (may have different content)"
    log "Response: $resp2"
  fi
}

# =============================================================================
# Scenario 4: MARKER triggers Step Function execution
# =============================================================================
scenario_4_step_function() {
  log "--- Scenario 4: MARKER → Step Function execution ---"
  local hour=$(date -u +%H)
  local schedule_id="h${hour}"

  # Write a test MARKER for earthquake-silver
  local ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local ttl=$(( $(date +%s) + 86400 ))
  aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --region "$REGION" \
    --item "{
      \"PK\":{\"S\":\"PIPELINE#earthquake-silver\"},
      \"SK\":{\"S\":\"MARKER#test-e2e#${ts}\"},
      \"scheduleID\":{\"S\":\"${schedule_id}\"},
      \"timestamp\":{\"S\":\"${ts}\"},
      \"ttl\":{\"N\":\"${ttl}\"}
    }" >/dev/null 2>&1

  # Wait for stream processing
  sleep 10

  # Check for Step Function execution via Terraform outputs
  local sfn_arn
  sfn_arn=$(cd "$(dirname "$0")/../deploy/terraform" && terraform output -raw state_machine_arn 2>/dev/null || echo "")

  if [ -z "$sfn_arn" ]; then
    warn "Could not find state_machine_arn from Terraform outputs"
    return
  fi

  local executions
  executions=$(aws stepfunctions list-executions \
    --state-machine-arn "$sfn_arn" \
    --max-results 10 \
    --region "$REGION" 2>/dev/null || echo "")

  if echo "$executions" | grep -q "earthquake-silver"; then
    pass "Step Function execution started for earthquake-silver"
  else
    warn "No Step Function execution found for earthquake-silver (may take longer)"
  fi
}

# =============================================================================
# Scenario 5: Silver pipeline completion
# =============================================================================
scenario_5_silver_pipeline() {
  log "--- Scenario 5: Silver pipeline completion check ---"
  local hour=$(date -u +%H)
  local schedule_id="h${hour}"

  log "Checking if earthquake-silver completed for schedule ${schedule_id}..."
  if wait_for_runlog "earthquake-silver" "$schedule_id" 300; then
    pass "Earthquake silver pipeline completed for ${schedule_id}"
  else
    warn "Earthquake silver pipeline not yet completed for ${schedule_id} (expected if first run)"
  fi
}

# =============================================================================
# Scenario 6: Custom evaluator endpoint
# =============================================================================
scenario_6_evaluator() {
  log "--- Scenario 6: Custom evaluator endpoint ---"

  local api_url
  api_url=$(cd "$(dirname "$0")/../deploy/terraform" && terraform output -raw evaluator_api_url 2>/dev/null || echo "")

  if [ -z "$api_url" ]; then
    warn "Could not find evaluator_api_url from Terraform outputs"
    return
  fi

  local resp
  resp=$(curl -s -X POST "${api_url}/evaluate/record-count" \
    -H "Content-Type: application/json" \
    -d "{\"bucket\":\"${BUCKET_NAME}\",\"prefix\":\"bronze/earthquake/\",\"minObjects\":1}" 2>/dev/null || echo "")

  if echo "$resp" | grep -qE "PASS|FAIL"; then
    pass "Custom evaluator responded with valid status"
    log "Evaluator response: $resp"
  else
    fail "Custom evaluator returned unexpected response"
    log "Response: $resp"
  fi
}

# =============================================================================
# Scenario 7: Chaos events tracking (if chaos enabled)
# =============================================================================
scenario_7_chaos() {
  log "--- Scenario 7: Chaos events tracking ---"

  local config
  config=$(aws dynamodb get-item \
    --table-name "$TABLE_NAME" \
    --key '{"PK":{"S":"CHAOS#CONFIG"},"SK":{"S":"CURRENT"}}' \
    --region "$REGION" 2>/dev/null || echo "")

  if [ -z "$config" ] || ! echo "$config" | grep -q "enabled"; then
    warn "No CHAOS#CONFIG found, skipping chaos validation"
    return
  fi

  # Check for any chaos events
  local events
  events=$(aws dynamodb query \
    --table-name "$TABLE_NAME" \
    --key-condition-expression "PK = :pk" \
    --expression-attribute-values '{":pk":{"S":"CHAOS#EVENTS"}}' \
    --region "$REGION" \
    --query 'Count' \
    --output text 2>/dev/null || echo "0")

  if [ "$events" != "0" ]; then
    log "Found ${events} chaos events"

    # Check for UNRECOVERED events (findings!)
    local unrecovered
    unrecovered=$(aws dynamodb query \
      --table-name "$TABLE_NAME" \
      --key-condition-expression "PK = :pk" \
      --filter-expression "#s = :status" \
      --expression-attribute-names '{"#s":"status"}' \
      --expression-attribute-values '{":pk":{"S":"CHAOS#EVENTS"},":status":{"S":"UNRECOVERED"}}' \
      --region "$REGION" \
      --query 'Count' \
      --output text 2>/dev/null || echo "0")

    if [ "$unrecovered" != "0" ]; then
      fail "Found ${unrecovered} UNRECOVERED chaos events (safety gaps to investigate!)"
    else
      pass "All chaos events recovered (no safety gaps found)"
    fi
  else
    warn "No chaos events found (chaos may not be enabled)"
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

  scenario_1_earthquake_ingestion
  scenario_2_crypto_ingestion
  scenario_3_dedup
  scenario_4_step_function
  scenario_5_silver_pipeline
  scenario_6_evaluator
  scenario_7_chaos

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
