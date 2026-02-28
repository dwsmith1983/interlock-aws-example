# Interlock AWS Example

A production-grade [medallion architecture](https://www.databricks.com/glossary/medallion-architecture) data pipeline on AWS, built to showcase [Interlock](https://github.com/dwsmith1983/interlock) — a STAMP-based safety framework for data pipeline reliability.

Two live data sources flow through bronze, silver, and gold tiers using Delta Lake on S3, with AWS Glue for transformations and Step Functions for orchestration. A **chaos testing framework** systematically probes every safety mechanism, and a **real-time dashboard** visualizes pipeline health, alerts, and chaos recovery.

## What This Showcases

This example demonstrates the core capabilities of the Interlock framework in a real AWS deployment:

| Interlock Feature | How It's Demonstrated |
|-------------------|----------------------|
| **STAMP readiness traits** | 5 traits per silver pipeline (source-freshness, record-count, hour-complete, sensor-freshness, data-quality), 2 per gold (upstream-dependency, record-count) |
| **Cascade orchestration** | Silver completion automatically triggers gold via DynamoDB Streams — no polling, no cron |
| **SLA enforcement** | Evaluation + completion deadlines per pipeline; watchdog detects missed schedules within 5 minutes |
| **Circuit breaker** | Orchestrator skips runs after N consecutive failures, prevents cascade amplification |
| **Idempotent reruns** | Delta MERGE ensures re-running any stage produces identical results |
| **Lock-based exclusion** | DynamoDB conditional writes prevent duplicate concurrent executions |
| **Archetype inheritance** | `silver-etl` and `gold-etl` archetypes define required/optional traits; pipelines inherit and override |
| **Chaos resilience** | 25 failure scenarios validate self-healing: auto-retry, lock recovery, data reconciliation |
| **Operational alerting** | Slack notifications, CloudWatch alarms, dead-letter queues, structured error tracking |

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
DynamoDB Streams                  ──> Pipeline Monitor
SNS Alerts Topic                  ──> Alert Logger ──> Slack
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

### Operational Hardening

The pipeline includes production-grade operational features beyond the core Interlock framework:

**Alerting** — SNS alerts topic feeds an alert-logger Lambda that persists `ALERT#` and `ERROR#` records to DynamoDB, updates `CONTROL#` pipeline health status, and forwards color-coded notifications to Slack (red=error, yellow=warning, green=info). CloudWatch alarms for Lambda errors and DLQ depth are wired to the same topic.

**Dead-letter queues** — Both DynamoDB Streams consumers (stream-router and pipeline-monitor) have SQS DLQs with 14-day retention. Failed records land in the DLQ rather than being silently dropped after retries.

**Circuit breaker** — The orchestrator checks `CONTROL#` consecutive failure count before starting a run. If failures exceed the threshold (default 5), the run is skipped with an alert. Prevents cascade amplification when a Glue job or evaluator is persistently failing.

**Rerun cap** — Drift-triggered reruns (late-arriving data) are capped at 5 per pipeline per day (configurable). Prevents unbounded reprocessing from repeated late arrivals.

**Watchdog lookback** — The missed-schedule detector only alerts on deadlines that passed within the last 15 minutes. Historical schedules (from before the pipeline was deployed) are silently ignored.

## Dashboard

A Next.js 15 static dashboard deployed to CloudFront + S3 provides real-time visibility into pipeline operations.

**Pages:**

| Page | Path | Description |
|------|------|-------------|
| Overview | `/` | Pipeline status cards, recent alerts, chaos status banner, run history |
| Pipeline Detail | `/pipeline/{id}` | Per-pipeline SLA metrics, 24-hour schedule grid, trait evaluation details |
| Run History | `/pipeline/{id}/history` | Full execution timeline, duration trends, record count progression |
| Alerts | `/alerts` | All alerts with severity, timestamps, SLA breach details |
| Chaos | `/chaos` | Chaos event timeline, recovery rate metrics, scenario breakdown by category |

**Deploy the dashboard:**

```bash
make dashboard-build    # Next.js static export
make dashboard-deploy   # Upload to S3 + CloudFront invalidation
```

The dashboard URL is shown in Terraform outputs after `make tf-apply`.

## Chaos Testing

A dedicated **chaos-controller Lambda** injects real failures to validate every safety mechanism in interlock. It runs every 20 minutes when enabled and covers 25 scenarios across 5 categories:

| Category | Scenarios | Examples |
|----------|-----------|---------|
| Infrastructure | 3 | Kill running Step Functions, throttle Lambdas to 0 concurrency |
| Data Plane | 5 | Delete/corrupt bronze files, corrupt Delta logs, inject schema drift |
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

Terraform creates ~100 resources:

| Resource | Count | Purpose |
|----------|-------|---------|
| DynamoDB | 1 table | Pipeline configs, run state, MARKERs, locks, observability (single-table design) |
| S3 | 2 buckets | Data (bronze/silver/gold + Glue scripts), Dashboard (static site) |
| Step Functions | 1 state machine | Orchestrates evaluate → trigger → poll → complete → cascade |
| Lambda (Go) | 6 | stream-router, orchestrator, evaluator, trigger, run-checker, watchdog |
| Lambda (Python) | 7 (+1) | ingest-earthquake, ingest-crypto, custom-evaluator, pipeline-monitor, dashboard-api, alert-logger, event-exporter (+chaos-controller if enabled) |
| Lambda Layer | 2 | Archetypes (YAML), Python shared (helpers + requests) |
| Glue | 5 jobs | silver-earthquake, silver-crypto, gold-earthquake, gold-crypto, compact-observability |
| EventBridge | 3 (+1) rules | 20-min ingestion triggers, 5-min watchdog (+chaos-controller if enabled) |
| API Gateway | 1 HTTP API | Evaluator endpoint for trait evaluation |
| SNS | 3 topics | Alerts, lifecycle signals, observability events |
| SQS | 2 DLQs | Dead-letter queues for stream-router and pipeline-monitor |
| CloudWatch | 8 alarms | Lambda error alarms (6) + DLQ depth alarms (2) |
| CloudFront | 1 distribution | Dashboard CDN |
| IAM | ~13 roles | Least-privilege roles per Lambda, Glue, Step Functions |

## Prerequisites

- [Go](https://go.dev/) 1.24+
- Python 3.12+
- Node.js 18+ (for dashboard)
- [Terraform](https://www.terraform.io/) 1.5+
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with credentials
- pip (for building the Python shared layer)

### Interlock Dependency

This project depends on the [interlock](https://github.com/dwsmith1983/interlock) Go module for the Lambda binaries. It is fetched automatically via the Go module proxy — no local clone required.

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
git clone https://github.com/dwsmith1983/interlock-aws-example.git
cd interlock-aws-example
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

### 5. (Optional) Configure Slack notifications

Create `deploy/terraform/secret.auto.tfvars` (gitignored):

```hcl
slack_webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

Then re-run `make tf-apply` to pick up the change.

### 6. Register pipelines

```bash
make seed
```

This registers all 4 pipelines (96 hourly schedules total) and seeds the chaos configuration.

### 7. Start the first ingestion

```bash
make kick    # invokes both ingest Lambdas immediately
```

After this, EventBridge triggers ingestion every 20 minutes. The full pipeline chain runs automatically:

```
ingest (20 min) → silver (hourly) → gold (hourly, cascade)
```

### 8. Deploy the dashboard

```bash
make dashboard-build
make dashboard-deploy
```

### Quick start

For a clean deploy with everything in one shot:

```bash
make fresh-start              # deploy + seed + kick
make fresh-start CHAOS=true   # deploy + seed + kick + enable chaos
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
aws_region                = "us-east-1"    # default: ap-southeast-1
table_name                = "my-pipeline"  # default: medallion-interlock
earthquake_rate_minutes   = 30             # default: 20
crypto_rate_minutes       = 30             # default: 20
glue_timeout_minutes      = 15             # default: 30
chaos_enabled             = true           # default: false
chaos_rate_minutes        = 10             # default: 20
circuit_breaker_threshold = 3              # default: 5
max_reruns_per_day        = 10             # default: 5
```

### Teardown

```bash
make tf-destroy
```

S3 buckets have `force_destroy = true`, so all data is deleted automatically.

## Project Structure

```
interlock-aws-example/
  archetypes/           Interlock archetype definitions (silver-etl, gold-etl)
  chaos/                Chaos scenario configuration (scenarios.yaml)
  cmd/seed/             Pipeline + chaos config registration tool
  dashboard/            Next.js 15 + Tailwind dashboard (5 pages, 13 components)
  deploy/
    build.sh            Builds Go Lambda binaries (auto-detects go.work) + stages layers
    statemachine.asl.json  Step Function ASL definition
    terraform/          All infrastructure-as-code (~100 resources)
      alarms.tf         CloudWatch alarms + Glue failure EventBridge rule
      chaos.tf          Chaos controller Lambda + EventBridge + IAM (conditional)
      dashboard.tf      CloudFront + S3 static site hosting
      dlq.tf            Dead-letter queues for stream consumers
      monitor.tf        Pipeline-monitor Lambda (DynamoDB Streams → CONTROL#/JOBLOG#)
      sns.tf            SNS topics + alert-logger + event-exporter Lambdas
      bootstrap/        Remote state backend (optional)
  e2e/                  End-to-end test suite
  glue/                 PySpark ETL scripts (silver + gold, per source)
  lambdas/
    alert_logger/       SNS → DynamoDB persistence + Slack forwarding
    chaos_controller/   Chaos injection engine (25 scenarios across 5 categories)
      scenarios/        Scenario implementations by category
      recovery.py       Recovery checker (INJECTED → RECOVERED/UNRECOVERED)
    dashboard_api/      HTTP API backend for dashboard data
    evaluator/          Custom trait evaluator (source-freshness, record-count, hour-complete)
    event_exporter/     Observability event consumer
    ingest_earthquake/  USGS earthquake data ingestion
    ingest_crypto/      CoinLore crypto ticker ingestion
    pipeline_monitor/   DynamoDB Streams → CONTROL# health + JOBLOG# records
    shared/             Python helpers (MARKER writer, S3 utils, chaos checks, observability)
  pipelines/            Pipeline YAML configs (traits, triggers, SLAs, schedules)
  Makefile              Build, deploy, seed, kick, chaos, dashboard, teardown
```

## Observability

All observability records use the DynamoDB single-table design with 30-day TTL:

| Record Type | Purpose | Query via GSI1PK |
|-------------|---------|-----------------|
| `PIPELINE#CONFIG` | Pipeline definitions (96 hourly schedules) | `PIPELINES` |
| `RUNLOG#` | Execution state per pipeline/schedule/date | `RUNLOGS` |
| `EVAL#` | Individual trait evaluation results | `EVALS` |
| `JOBLOG#` | Glue job analytics (duration, record counts, tier/source) | `JOBLOGS` |
| `ERROR#` | Failure records with resolution tracking | `ERRORS` |
| `ALERT#` | Alert persistence (SLA breach, errors, chaos) | `ALERTS` |
| `CONTROL#` | Pipeline health (consecutive failures, last success, circuit breaker state) | `CONTROLS` |
| `CHAOS#` | Chaos injection lifecycle (injected/detected/recovered) | `CHAOS` |
| `MARKER#` | Ingestion + cascade completion signals | — |
| `LOCK#` | Distributed locks for execution exclusion | — |
| `DEDUP#` | Deduplication records | — |
| `RERUN#` | Drift-triggered rerun tracking | — |

## Cost

With default settings (G.1X Glue, 2 workers, 20-min ingestion):

- **Glue**: ~\$0.44/DPU-hour. Each job runs 1-3 minutes. With 4 jobs x 24 hours = ~96 runs/day. At ~2 min average: ~\$6/day.
- **Lambda**: Negligible (millisecond durations, free tier covers most).
- **DynamoDB**: Pay-per-request, negligible at this scale.
- **Step Functions**: \$0.025 per 1000 state transitions. ~\$0.10/day.
- **S3 + CloudFront**: Storage and CDN costs minimal for this data volume.

**Estimated total: ~\$6-8/day** (dominated by Glue). Reduce by increasing ingestion intervals or running fewer hours.
