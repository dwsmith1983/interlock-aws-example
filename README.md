# Medallion Pipeline

A production-grade [medallion architecture](https://www.databricks.com/glossary/medallion-architecture) data pipeline on AWS, orchestrated by [Interlock](https://github.com/dwsmith1983/interlock) — a STAMP-based safety framework for data pipeline reliability.

Two live data sources flow through bronze, silver, and gold tiers using Delta Lake on S3, with AWS Glue for transformations and Step Functions for orchestration.

## Architecture

```
EventBridge (hourly)
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
```

### Data Sources

| Source | Type | Frequency | Description |
|--------|------|-----------|-------------|
| [GH Archive](https://www.gharchive.org/) | HTTP | Hourly | GitHub public event stream (~150k events/hour) |
| [Open-Meteo](https://open-meteo.com/) | REST API | Hourly | Weather observations for major cities |

### Tiers

**Bronze** — Raw data as-is from source. JSONL files partitioned by `dt={date}/hh={hour}/`. Auto-expires after 30 days via S3 lifecycle.

**Silver** — Cleaned and deduplicated Delta tables. Flattened schemas, type enforcement, dedup by natural key (`event_id` for GH Archive, `city+observation_time` for Open-Meteo). Partitioned by `dt`.

**Gold** — Aggregated analytics tables. Daily rollups that incrementally update via Delta MERGE as each hourly silver completes:

- `gharchive/hourly_by_type/` — Event counts by type and hour
- `gharchive/top_repos/` — Top 10 repositories by event count
- `gharchive/org_activity/` — Organization activity metrics
- `openmeteo/daily_city/` — Daily weather summary per city (min/max/avg temp, precipitation)
- `openmeteo/daily_global/` — Cross-city daily comparison

### How Cascade Works

Each pipeline has 24 hourly schedules (`h00`–`h23`). When silver `h13` completes:

1. The state machine's `NotifyDownstream` step writes a cascade MARKER for gold `h13`
2. DynamoDB Streams delivers the MARKER to the stream-router Lambda
3. Stream-router starts a new Step Function execution for gold `h13`
4. Gold evaluates its traits (upstream-dependency checks silver `h13` completed, record-count checks silver data exists)
5. Gold Glue job reads ALL silver data for the date and produces daily aggregations via Delta MERGE

Gold runs after every hourly silver, progressively refining the day's aggregations. Delta MERGE makes this idempotent — running gold multiple times with the same data produces identical results.

## AWS Resources

Terraform creates ~80 resources:

| Resource | Count | Purpose |
|----------|-------|---------|
| DynamoDB | 1 table | Pipeline configs, run state, MARKERs, locks (single-table design) |
| S3 | 1 bucket | Bronze/silver/gold data + Glue scripts |
| Step Functions | 1 state machine | Orchestrates evaluate → trigger → poll → complete → cascade |
| Lambda (Go) | 5 | stream-router, orchestrator, evaluator, trigger, run-checker |
| Lambda (Python) | 4 | ingest-gharchive, ingest-openmeteo, custom-evaluator, alert-logger |
| Lambda Layer | 2 | Archetypes (YAML), Python shared (helpers + requests) |
| Glue | 4 jobs | silver-gharchive, silver-openmeteo, gold-gharchive, gold-openmeteo |
| EventBridge | 2 rules | Hourly triggers for each ingestion Lambda |
| API Gateway | 1 HTTP API | Evaluator endpoint for trait evaluation |
| SNS | 1 topic | Alert notifications (SLA breach, errors) |
| IAM | ~12 roles | Least-privilege roles per Lambda, Glue, Step Functions |

## Prerequisites

- [Go](https://go.dev/) 1.24+
- Python 3.12+
- [Terraform](https://www.terraform.io/) 1.5+
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with credentials
- pip (for building the Python shared layer)

### Interlock Dependency

This project depends on the [interlock](https://github.com/dwsmith1983/interlock) Go module (`v0.1.0`) for the Lambda binaries. It is fetched automatically via the Go module proxy — no local clone required.

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

### 5. Register pipelines

```bash
make seed
```

### 6. Start the first ingestion

```bash
make kick    # invokes both ingest Lambdas immediately
```

After this, EventBridge triggers ingestion hourly. The full pipeline chain runs automatically:

```
ingest → silver → gold (cascade)
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
aws_region           = "us-east-1"       # default: ap-southeast-1
table_name           = "my-pipeline"     # default: medallion-interlock
gharchive_rate_minutes = 120             # default: 60
openmeteo_rate_minutes = 120             # default: 60
glue_timeout_minutes   = 15              # default: 30
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
  cmd/seed/             Pipeline registration tool
  deploy/
    build.sh            Fetches interlock module + builds Go Lambda binaries + stages layers
    statemachine.asl.json  Step Function ASL definition
    terraform/          All infrastructure-as-code
      bootstrap/        Remote state backend (optional)
  glue/                 PySpark ETL scripts (silver + gold, per source)
  lambdas/
    evaluator/          Custom trait evaluator (source-freshness, record-count, upstream-dependency)
    ingest_gharchive/   GH Archive data ingestion
    ingest_openmeteo/   Open-Meteo data ingestion
    alert_logger/       SNS subscriber — logs alerts to CloudWatch + DynamoDB
    shared/             Python helpers (MARKER writer, S3 utils)
  pipelines/            Pipeline YAML configs (traits, triggers, schedules)
  Makefile              Build, deploy, seed, kick, teardown
```

## Cost

With default settings (G.1X Glue, 2 workers, hourly ingestion):

- **Glue**: ~\$0.44/DPU-hour. Each job runs 1-3 minutes. With 4 jobs x 24 hours = ~96 runs/day. At ~2 min average: ~\$6/day.
- **Lambda**: Negligible (millisecond durations, free tier covers most).
- **DynamoDB**: Pay-per-request, negligible at this scale.
- **Step Functions**: \$0.025 per 1000 state transitions. ~\$0.10/day.
- **S3**: Storage costs minimal for this data volume.

**Estimated total: ~\$6-8/day** (dominated by Glue). Reduce by increasing ingestion intervals or running fewer hours.


