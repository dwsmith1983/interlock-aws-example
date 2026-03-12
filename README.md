# interlock-aws-example

Production-grade telecom ETL pipeline demonstrating [Interlock](https://github.com/dwsmith1983/interlock) pipeline orchestration on AWS. Generates synthetic CDR and SEQ data, processes it through a bronze/silver medallion architecture, and orchestrates the full pipeline with SLA monitoring.

**Interlock framework:** [github.com/dwsmith1983/interlock](https://github.com/dwsmith1983/interlock) | [Documentation](https://dwsmith1983.github.io/interlock)

## Architecture

```
EventBridge (rate 15m)
  |- CDR rule --> telecom-generator Lambda --> S3 raw cdr/
  |- SEQ rule --> telecom-generator Lambda --> S3 raw seq/
  |- rate(10m) -> dryrun-demo Lambda -> S3 dryrun-demo/ + sensors (dry run only)
                                                  |
                                          EventBridge S3 PutObject
                                                  |
                                            Kinesis Stream
                                                  |
                                        bronze-consumer Lambda
                                          |- Write Delta Lake (bronze/)
                                          |- Update hourly-status sensor
                                          |- Update daily-status sensor
                                                  |
                                    Interlock Control Table (DynamoDB)
                                          |
                        DynamoDB Streams --> stream-router Lambda
                                          |
                    +---------------------+---------------------+
                    |                                           |
          hourly-status sensor                       daily-status sensor
          (complete = true)                     (all_hours_complete = true)
                    |                                           |
          Step Functions (per hour)                 Step Functions (per day)
          |- orchestrator: Glue agg-hour            |- orchestrator: Glue agg-day
          |- sla-monitor: deadline :30              |- sla-monitor: deadline 02:00
          |- Write silver/{stream}_agg_hour/        |- Write silver/{stream}_agg_day/
```

Two data streams flow through three layers:

| Layer | Description | Trigger |
|-------|-------------|---------|
| **Raw** | Gzipped JSONL from generator Lambda | EventBridge rate(15 min) |
| **Bronze** | Delta Lake with hashed phone numbers | Kinesis (S3 PutObject events) |
| **Silver** | Spark aggregations (hourly + daily) | Interlock sensor-driven |

### Interlock Orchestration

Seven pipelines are defined in `pipelines/` as declarative YAML:

| Pipeline | Type | Trigger | Job |
|----------|------|---------|-----|
| `bronze-cdr` | Event | Sensor `hourly-status` complete | Audit Lambda |
| `bronze-seq` | Event | Sensor `hourly-status` complete | Audit Lambda |
| `silver-cdr-hour` | Event | Sensor `audit-result` match | Glue `cdr-agg-hour` |
| `silver-seq-hour` | Event | Sensor `audit-result` match | Glue `seq-agg-hour` |
| `silver-cdr-day` | Event | Sensor `daily-status` all hours | Glue `cdr-agg-day` |
| `silver-seq-day` | Event | Sensor `daily-status` all hours | Glue `seq-agg-day` |
| `dryrun-weather` | Dry run | Sensor `weather-ready` complete | *(observation only)* |

Silver pipelines are fully event-driven — no cron schedules. The bronze consumer writes per-period sensor records to DynamoDB (one row per hour, one per day). When a sensor satisfies the trigger condition, the stream-router starts a Step Functions execution for that period.

### Per-Hour Execution Model

Each hour gets its own sensor record and SFN execution:

- Sensor key: `SENSOR#hourly-status#2026-03-04T10`
- Execution name encodes the hour: `silver-cdr-hour-2026-03-04T10-...`
- Glue receives `--par_day` and `--par_hour` arguments
- SLA deadline `:30` resolves to `T10:30:00Z` for hour 10

Daily pipelines accumulate completed hours in a StringSet. When all 24 arrive, `all_hours_complete=true` fires the daily SFN.

### Dry Run Demo

The `dryrun-weather` pipeline demonstrates Interlock's dry run mode (`dryRun: true`). It evaluates trigger conditions and SLA timing against real sensor data but never starts Step Function executions — letting teams observe Interlock behavior alongside existing scheduled pipelines before switching to full control.

**How it works:**

1. EventBridge invokes `dryrun-demo` Lambda every 10 minutes (6x/hour)
2. Each invocation generates a variable batch of weather station readings (1-6 stations, time-of-day weighted)
3. Lambda writes readings to S3 (`dryrun-demo/par_day=YYYYMMDD/par_hour=HH/`)
4. Lambda updates two sensors in the Interlock control table:
   - `weather-ready` — trigger sensor tracking `total_readings`, `valid_readings`, and `complete`
   - `weather-audit` — post-run sensor tracking `total_readings` for drift detection
5. When `total_readings >= 12 AND valid_pct >= 0.75`, the stream-router emits dry run events

**Events emitted (all observation-only, no executions started):**

| Event | When |
|-------|------|
| `DRY_RUN_WOULD_TRIGGER` | Trigger condition met |
| `DRY_RUN_SLA_PROJECTION` | SLA met/breach estimate (deadline `:45`) |
| `DRY_RUN_LATE_DATA` | Sensor updated after trigger fired |
| `DRY_RUN_DRIFT` | Audit reading count diverged from baseline |

**Variation model:** Batch sizes vary by time of day (day hours 06-23 UTC average ~3.7 readings; night hours 00-05 UTC average ~2.2). About 15% of readings are degraded quality (< 0.7). This produces natural variation — some hours trigger early with margin, others trigger late or not at all.

**Manual test:**

```bash
# Invoke once
aws lambda invoke --function-name dev-dryrun-demo --payload '{}' /tmp/out.json
cat /tmp/out.json

# Check sensors
aws dynamodb query --table-name dev-interlock-control \
  --key-condition-expression 'PK = :pk AND begins_with(SK, :sk)' \
  --expression-attribute-values '{":pk":{"S":"PIPELINE#dryrun-weather"},":sk":{"S":"SENSOR#"}}' \
  --query 'Items[*].{SK:SK.S,data:data.M}'

# Invoke 4-5 more times to trigger completion, then check for DRY_RUN markers
```

## Data Streams

- **CDR (Call Detail Records)** — probe-level pings from phone calls (~100M records/day default)
- **SEQ (Sequence/Probe)** — probe-level pings from internet browsing (~500M records/day default)

### Schemas

**CDR** — one row per ~10s probe ping during a phone call:
```json
{"phone_out": "2125551234", "phone_in": "3109876543", "cell_tower": "3f7a2b1c", "time": "2026-03-01T14:03:27Z"}
```

**SEQ** — one row per ~10s probe ping during internet browsing:
```json
{"phone_number": "4695551234", "cell_tower": "a8c2e4f1", "host_name": "www.youtube.com", "site_name": "YouTube", "time": "2026-03-01T14:07:12Z"}
```

### Session Model

Records are generated from temporally correlated **sessions**, not independent random samples:

- **CDR**: Each phone call is a session (exponential duration, mean ~2 min). A 2-minute call produces ~12 consecutive records with the same phone pair. 90% stationary (same tower), 10% mobile (tower handoffs via adjacency graph).
- **SEQ**: Each browsing session is 10-60 minutes with 3-15 site visits. Within a site visit, host_name is constant. Streaming sites (YouTube, Netflix) produce more pings.

Traffic follows a bimodal time-of-day distribution (peaks at 10 AM and 8 PM, trough at 3 AM). Generation is **deterministic and idempotent** — seeded by `sha256(stream + window_start)`.

## S3 Layout

```
s3://{bucket}/
  {stream}/par_day=YYYYMMDD/par_hour=HH/{stream}_{YYYYMMDD}_{HHMM}_{part}.jsonl.gz  (raw)
  bronze/{stream}/par_day=YYYYMMDD/par_hour=HH/*.parquet                              (Delta)
  silver/{stream}_agg_hour/par_day=YYYYMMDD/par_hour=HH/*.parquet                     (Delta)
  silver/{stream}_agg_day/par_day=YYYYMMDD/*.parquet                                  (Delta)
```

Each raw file contains up to 100K records (~1.5-3 MB gzipped). Bronze and silver layers use Delta Lake format.

## Reference Data

- **2000 cell towers** across 50 US metro areas (~40 per metro) with adjacency graph for mobility
- **500K phone numbers** (seeded, deterministic)
- **~500 websites** with Zipf popularity weights

## Deployment

### Prerequisites

- AWS CLI configured
- Terraform >= 1.5
- Python 3.12
- Go 1.24 (for building Interlock Lambdas)
- Docker (for building the Delta Lake Lambda layer)

### Build and Deploy

```bash
# Build the Delta Lake layer (one-time, requires Docker)
make build-delta-layer

# Build all Lambda and Glue artifacts
make build-all

# Initialize and deploy infrastructure
make tf-init
make tf-apply

# Restart EventBridge schedules (required after first deploy)
make restart-schedules
```

Or in one step after initial `tf-init`:

```bash
make deploy   # runs tf-apply + restart-schedules
```

### Backfill Historical Data

```bash
# Generate data from a specific date to now
./scripts/backfill.sh 2026-03-01
```

The backfill script invokes the generator Lambda for every 15-minute window from the start date to the current time.

### Manual Invocation

```bash
# Test CDR generation for a specific window
aws lambda invoke --function-name dev-telecom-generator \
  --payload '{"stream":"cdr","daily_target":1000000}' /dev/stdout

# Check output
aws s3 ls s3://{bucket}/cdr/ --recursive
```

### Teardown

```bash
# Empty S3 bucket first (required for destroy)
aws s3 rm s3://{bucket} --recursive

make tf-destroy
```

## Cost Estimate

Costs depend heavily on data volume. Glue is the primary cost driver.

| Resource | What Drives Cost | Est. Monthly |
|----------|-----------------|-------------|
| **Glue** (4 jobs) | 50 runs/day × 2-5 G.1X workers | $50-300 |
| **Lambda** (7 functions) | Generator 3 GB × 60s, bronze 2 GB × 10s | $8-15 |
| **S3** | 7-day lifecycle, ~15 GB/day at full scale | $3-5 |
| **CloudWatch** | 7-day log retention, ~5 GB/month ingested | $2-3 |
| **DynamoDB** (4 tables) | On-demand, low volume | $1-2 |
| **Step Functions** | ~50 executions/day × 12 transitions | < $1 |
| **Kinesis** | On-demand, ~2K events/day | < $1 |
| **EventBridge** | ~3K events/day | < $1 |
| **Total** | | **$65-330** |

**Reducing costs:**
- Lower `cdr_daily_target` / `seq_daily_target` in `variables.tf` — Glue jobs finish faster
- Reduce `glue_hourly_workers` from 2 to 1
- Stop EventBridge schedules when not testing (`make restart-schedules` to resume)
- At minimum scale (~1M records/day), expect ~$30-50/month

## Project Structure

```
generator/
    handler.py              # Lambda entry point
    sessions.py             # Session generation (CDR calls, SEQ browsing)
    generate.py             # Sessions -> records -> S3
    distribution.py         # Time-of-day traffic distribution
    phones.py               # 500K phone number pool
    towers.py               # Tower loading, adjacency, mobility
    websites.py             # ~500 weighted domains
    reference/
        towers.json         # Static tower data (2000 entries)
bronze_consumer/
    handler.py              # Kinesis Lambda entry point
    sensor.py               # Hourly/daily sensor updates to Interlock control table
    delta_writer.py         # Write records to Delta Lake
    hasher.py               # SHA-256 phone number hashing
    s3_reader.py            # Read gzipped JSONL from S3
audit/
    handler.py              # Hourly reconciliation (Delta count vs sensor count)
glue_jobs/
    args.py                 # Argument resolution (--par_day, --par_hour, --s3_bucket)
    components.py           # ReadBronzeDelta, CdrAggTransform, SeqAggTransform, WriteSilverDelta
    cdr_agg_hour.py         # Hourly CDR aggregation
    cdr_agg_day.py          # Daily CDR aggregation
    seq_agg_hour.py         # Hourly SEQ aggregation
    seq_agg_day.py          # Daily SEQ aggregation
pipelines/
    bronze-cdr.yaml         # Bronze CDR audit pipeline
    bronze-seq.yaml         # Bronze SEQ audit pipeline
    silver-cdr-hour.yaml    # Silver CDR hourly aggregation
    silver-seq-hour.yaml    # Silver SEQ hourly aggregation
    silver-cdr-day.yaml     # Silver CDR daily aggregation
    silver-seq-day.yaml     # Silver SEQ daily aggregation
    dryrun-weather.yaml     # Dry run demo — weather station aggregation (observation only)
lambdas/
    dryrun_demo/
        handler.py          # Weather station simulation (EventBridge 10-min schedule)
        requirements.txt
scripts/
    backfill.sh             # Historical data generation
    build_interlock.sh      # Build Go Lambda binaries from interlock repo
    build_delta_layer.sh    # Build pyarrow/deltalake Lambda layer via Docker
    gen_towers.py           # One-time tower reference data generator
deploy/
    terraform/              # All infrastructure (108 resources)
```
