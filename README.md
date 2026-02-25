# Medallion Pipeline

A production-grade [medallion architecture](https://www.databricks.com/glossary/medallion-architecture) data pipeline on AWS, orchestrated by [Interlock](https://github.com/dwsmith1983/interlock) — a STAMP-based safety framework for data pipeline reliability.

Two live data sources flow through bronze, silver, and gold tiers using Delta Lake on S3, with AWS Glue for transformations and Step Functions for orchestration. Includes a **chaos testing framework** that systematically probes every safety mechanism in interlock.

## Architecture

```
EventBridge (20 min)
    |
    v
Ingest Lambda ──> S3 bronze/ + DynamoDB MARKER
                                    |
                                    v
                          Stream Router Lambda
                                    |
                                    v
                        Step Function Execution
                          |                |
                     Evaluator        Orchestrator
                     (per-trait)       (readiness)
                          |                |
                          v                v
                        Glue Job ──> S3 silver/
                                         |
                                    NotifyDownstream
                                    (cascade MARKER)
                                         |
                                         v
                              Stream Router (again)
                                         |
                                         v
                              Step Function (gold)
                                    |         |
                               Evaluator  Orchestrator
                                    |         |
                                    v         v
                                  Glue Job ──> S3 gold/

EventBridge (20 min, conditional) ──> Chaos Controller
EventBridge (5 min)               ──> SLA Watchdog
```

### Data Sources

| Source | Type | Frequency | Description |
|--------|------|-----------|-------------|
| [USGS Earthquakes](https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson) | GeoJSON | Every 20 min | Rolling 1-hour window of global seismic events (~50-500/hour) |
| [CoinLore Crypto](https://api.coinlore.net/api/tickers/) | REST API | Every 20 min | Top 100 cryptocurrencies by market cap |

Both sources are free, require no authentication, and have no rate limits at 20-minute cadence.

### Tiers

**Bronze** — Raw data as-is from source. JSONL files partitioned by `par_day={YYYYMMDD}/par_hour={HH}/`. Auto-expires after 30 days via S3 lifecycle. Three files per source per hour (one per 20-min ingestion).

**Silver** — Cleaned and deduplicated Delta tables. Flattened schemas, type enforcement, dedup by natural key (`earthquake_id` for earthquakes, `coin_id+snapshot_time` for crypto). Partitioned by `par_day`, with `par_hour` as a column.

**Gold** — Aggregated analytics tables. Re-computed idempotently via Delta MERGE each hour:

- `earthquake/hourly_summary/` — Event count, avg/max magnitude, depth stats, tsunami count per hour
- `earthquake/daily_summary/` — Total events, distinct types/networks, significant events per day
- `earthquake/magnitude_distribution/` — Events bucketed by magnitude range (0-1, 1-2, ..., 5+)
- `earthquake/geographic_hotspots/` — Events by 10-degree lat/lon grid, avg/max magnitude
- `crypto/daily_market/` — Total market cap, volume, avg/median % change per day
- `crypto/top_movers/` — Top 10 gainers + top 10 losers by 24h % change

### How Cascade Works

Each pipeline has 24 hourly schedules (`h00`–`h23`). When silver `h13` completes:

1. The state machine's `NotifyDownstream` step writes a cascade MARKER for gold `h13`
2. DynamoDB Streams delivers the MARKER to the stream-router Lambda
3. Stream-router starts a new Step Function execution for gold `h13`
4. Gold evaluates its traits (upstream-dependency checks silver `h13` completed, record-count checks silver data exists)
5. Gold Glue job reads ALL silver data for the date and produces daily aggregations via Delta MERGE

Gold runs after every hourly silver, progressively refining the day's aggregations. Delta MERGE makes this idempotent — running gold multiple times with the same data produces identical results.

### Pipeline SLAs

| Pipeline | Eval Deadline | Completion Deadline | Rationale |
|----------|---------------|---------------------|-----------|
| `earthquake-silver` | +20 min | +35 min | Ingestion every 20m, eval should start quickly |
| `earthquake-gold` | +40 min | +55 min | Cascades from silver |
| `crypto-silver` | +20 min | +35 min | Same cadence as earthquake |
| `crypto-gold` | +40 min | +55 min | Cascades from silver |

## Chaos Testing

A dedicated **chaos-controller Lambda** injects real failures to validate every safety mechanism in interlock. It runs every 20 minutes when enabled and covers 25 scenarios across 5 categories:

| Category | Scenarios | Examples |
|----------|-----------|---------|
| Infrastructure | 3 | Kill running Step Functions, throttle Lambdas to 0 concurrency |
| Data Plane | 5 | Delete/corrupt bronze files, corrupt Delta logs, write to wrong partition |
| Control Plane | 5 | Delete locks, corrupt RunLogs, force CAS conflicts, delete pipeline configs |
| Trigger/Cascade | 6 | Duplicate/burst MARKERs, future/late data, break upstream dependencies |
| Evaluator | 4 | Block evaluations, inject delays, force false passes, duplicate ingestion |

Each scenario has severity gating (mild/moderate/severe), cooldown enforcement, and recovery tracking:

```
INJECTED → DETECTED → RECOVERED (or UNRECOVERED after timeout)
```

**UNRECOVERED** events are findings — they indicate a gap in interlock's safety mechanisms.

### Chaos Commands

```bash
make chaos-enable                    # Enable with default severity (moderate)
make chaos-enable SEVERITY=severe    # Enable all scenarios
make chaos-disable                   # Immediate kill switch
make chaos-status                    # Show all chaos events by status
make chaos-report                    # Summary counts (injected/detected/recovered/unrecovered)
make chaos-history                   # Full timeline
```

### Severity Levels

- **mild** — Always runs when chaos enabled (dup-marker, empty-bronze, wrong-partition, dup-data, orphan-marker)
- **moderate** — Runs at moderate+ (delete-bronze, corrupt-bronze, corrupt-runlog, burst-markers, eval-block, eval-slow)
- **severe** — Only at severe (sfn-kill, lambda-throttle, corrupt-delta-log, delete-lock, delete-config, eval-false-pass)

## AWS Resources

Terraform creates ~85 resources:

| Resource | Count | Purpose |
|----------|-------|---------|
| DynamoDB | 1 table | Pipeline configs, run state, MARKERs, locks, observability (single-table design) |
| S3 | 1 bucket | Bronze/silver/gold data + Glue scripts |
| Step Functions | 1 state machine | Orchestrates evaluate → trigger → poll → complete → cascade |
| Lambda (Go) | 6 | stream-router, orchestrator, evaluator, trigger, run-checker, watchdog |
| Lambda (Python) | 4 (+1) | ingest-earthquake, ingest-crypto, custom-evaluator, alert-logger (+chaos-controller if enabled) |
| Lambda Layer | 2 | Archetypes (YAML), Python shared (helpers + requests) |
| Glue | 4 jobs | silver-earthquake, silver-crypto, gold-earthquake, gold-crypto |
| EventBridge | 3 (+1) rules | 20-min triggers for ingestion, 5-min watchdog (+chaos-controller if enabled) |
| API Gateway | 1 HTTP API | Evaluator endpoint for trait evaluation |
| SNS | 1 topic | Alert notifications (SLA breach, errors) |
| IAM | ~13 roles | Least-privilege roles per Lambda, Glue, Step Functions |

## Prerequisites

- [Go](https://go.dev/) 1.24+
- Python 3.12+
- [Terraform](https://www.terraform.io/) 1.5+
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with credentials
- pip (for building the Python shared layer)

### Interlock Dependency

This project depends on the [interlock](https://github.com/dwsmith1983/interlock) Go module (`v0.1.1`) for the Lambda binaries. It is fetched automatically via the Go module proxy — no local clone required.

For local development with unpublished interlock changes, create a `go.work` file:

```
go 1.24.0
use (
    .
    ../interlock
)
```

The build script auto-detects `go.work` and builds from the local workspace instead of the module cache.

## Deploy

### 1. Clone the repository

```bash
git clone https://github.com/dwsmith1983/medallion-pipeline.git
cd medallion-pipeline
```

### 2. (Optional) Bootstrap remote Terraform state

Skip this step to use local state. For shared/persistent state:

```bash
make tf-bootstrap
# Then uncomment the backend "s3" block in deploy/terraform/main.tf
```

### 3. Initialize Terraform

```bash
make tf-init
```

### 4. Build and deploy

```bash
make tf-apply    # builds Lambda binaries, then runs terraform apply
```

To enable chaos testing:

```bash
cd deploy/terraform
terraform apply -var="chaos_enabled=true"
```

### 5. Register pipelines

```bash
make seed
```

This registers all 4 pipelines (96 hourly schedules total) and seeds the chaos configuration.

### 6. Start the first ingestion

```bash
make kick    # invokes both ingest Lambdas immediately
```

After this, EventBridge triggers ingestion every 20 minutes. The full pipeline chain runs automatically:

```
ingest (20 min) → silver (hourly) → gold (hourly, cascade)
```

### Verify

Check Step Function executions in the AWS console or:

```bash
aws stepfunctions list-executions \
  --state-machine-arn $(cd deploy/terraform && terraform output -raw state_machine_arn) \
  --query 'executions[].{name:name,status:status}' \
  --output table
```

You should see silver and gold executions for both data sources, all `SUCCEEDED`.

### Customization

Override defaults via Terraform variables or `terraform.tfvars`:

```hcl
aws_region              = "us-east-1"    # default: ap-southeast-1
table_name              = "my-pipeline"  # default: medallion-interlock
earthquake_rate_minutes = 30             # default: 20
crypto_rate_minutes     = 30             # default: 20
glue_timeout_minutes    = 15             # default: 30
chaos_enabled           = true           # default: false
chaos_rate_minutes      = 10             # default: 20
```

### Teardown

```bash
make tf-destroy
```

S3 bucket has `force_destroy = true`, so all data is deleted automatically.

## Project Structure

```
medallion-pipeline/
  archetypes/           Interlock archetype definitions (silver-etl, gold-etl)
  chaos/                Chaos scenario configuration (scenarios.yaml)
  cmd/seed/             Pipeline + chaos config registration tool
  deploy/
    build.sh            Builds Go Lambda binaries (auto-detects go.work) + stages layers
    statemachine.asl.json  Step Function ASL definition
    terraform/          All infrastructure-as-code
      chaos.tf          Chaos controller Lambda + EventBridge + IAM (conditional)
      bootstrap/        Remote state backend (optional)
  e2e/                  End-to-end test suite
  glue/                 PySpark ETL scripts (silver + gold, per source)
  lambdas/
    chaos_controller/   Chaos injection engine (25 scenarios across 5 categories)
      scenarios/        Scenario implementations (infrastructure, data, control, cascade, evaluator)
      recovery.py       Recovery checker (INJECTED → RECOVERED/UNRECOVERED)
    evaluator/          Custom trait evaluator (source-freshness, record-count, upstream-dependency)
    ingest_earthquake/  USGS earthquake data ingestion
    ingest_crypto/      CoinLore crypto ticker ingestion
    alert_logger/       SNS subscriber — logs alerts + writes ERROR#/CONTROL# records
    shared/             Python helpers (MARKER writer, S3 utils, chaos checks, observability)
  pipelines/            Pipeline YAML configs (traits, triggers, SLAs, schedules)
  Makefile              Build, deploy, seed, kick, chaos, teardown
```

## Observability

All observability records use the DynamoDB single-table design with 30-day TTL:

| Record Type | Purpose | Query via GSI1PK |
|-------------|---------|-----------------|
| `EVAL#` | Individual trait evaluation results | `EVALS` |
| `ERROR#` | Failure records with resolution tracking | `ERRORS` |
| `CHAOS#` | Chaos injection lifecycle (injected/detected/recovered) | `CHAOS` |
| `CONTROL#` | Pipeline health dashboard (consecutive failures, last success) | `CONTROLS` |
| `ALERT#` | Alert persistence (SLA breach, errors) | `ALERTS` |

## Cost

With default settings (G.1X Glue, 2 workers, 20-min ingestion):

- **Glue**: ~\$0.44/DPU-hour. Each job runs 1-3 minutes. With 4 jobs x 24 hours = ~96 runs/day. At ~2 min average: ~\$6/day.
- **Lambda**: Negligible (millisecond durations, free tier covers most).
- **DynamoDB**: Pay-per-request, negligible at this scale.
- **Step Functions**: \$0.025 per 1000 state transitions. ~\$0.10/day.
- **S3**: Storage costs minimal for this data volume.

**Estimated total: ~\$6-8/day** (dominated by Glue). Reduce by increasing ingestion intervals or running fewer hours.
