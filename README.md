# interlock-aws-example

Synthetic telecom data generator for demonstrating [Interlock](https://github.com/dwsmith1983/interlock) pipeline orchestration on AWS.

## Architecture

A single Python Lambda (`telecom-generator`) is invoked by two EventBridge rules every 15 minutes, producing two data streams:

- **CDR (Call Detail Records)** — probe-level pings from phone calls (~100M records/day)
- **SEQ (Sequence/Probe)** — probe-level pings from internet browsing (~500M records/day)

```
EventBridge (rate 15 min)
    |-- CDR rule --> telecom-generator Lambda --> S3 cdr/...
    |-- SEQ rule --> telecom-generator Lambda --> S3 seq/...
```

The generator simulates an external telecom provider's ingestion feed. It is **not** part of the Interlock-orchestrated ETL pipeline — it produces the raw data that the pipeline will process.

## Data Schemas

**CDR** — one row per ~10s probe ping during a phone call:
```json
{"phone_out": "2125551234", "phone_in": "3109876543", "cell_tower": "3f7a2b1c", "time": "2026-03-01T14:03:27Z"}
```

**SEQ** — one row per ~10s probe ping during internet browsing:
```json
{"phone_number": "4695551234", "cell_tower": "a8c2e4f1", "host_name": "www.youtube.com", "site_name": "YouTube", "time": "2026-03-01T14:07:12Z"}
```

## Session Model

Records are **not** independent random samples. They are generated from temporally correlated **sessions**:

- **CDR**: Each phone call is a session (exponential duration, mean ~2 min). A 2-minute call produces ~12 consecutive records with the same phone pair. 90% stationary (same tower), 10% mobile (tower handoffs via adjacency graph).
- **SEQ**: Each browsing session is 10-60 minutes with 3-15 site visits. Within a site visit, host_name is constant. Streaming sites (YouTube, Netflix) produce more pings.

Traffic follows a bimodal time-of-day distribution (peaks at 10 AM and 8 PM, trough at 3 AM). Generation is **deterministic and idempotent** — seeded by `sha256(stream + window_start)`.

## S3 Layout

```
s3://{bucket}/{stream}/par_day=YYYYMMDD/par_hour=HH/{stream}_{YYYYMMDD}_{HHMM}_{part:04d}.jsonl.gz
```

Each file contains up to 100K records (~1.5-3 MB gzipped).

## Reference Data

- **2000 cell towers** across 50 US metro areas (~40 per metro) with adjacency graph for mobility
- **500K phone numbers** (seeded, deterministic)
- **~500 websites** with Zipf popularity weights

## Deployment

### Prerequisites

- AWS CLI configured
- Terraform >= 1.5
- Python 3.12

### Build and Deploy

```bash
# Package the Lambda
make build-generator

# Initialize and apply Terraform
make tf-init
make tf-apply
```

### Manual Invocation

```bash
# Test CDR generation (small scale)
aws lambda invoke --function-name dev-telecom-generator \
  --payload '{"stream":"cdr","daily_target":1000000}' /dev/stdout

# Check output
aws s3 ls s3://{bucket}/cdr/ --recursive
```

### Teardown

```bash
make tf-destroy
```

## Cost Estimate

~$6/month (Lambda compute ~$2.40, S3 storage ~$2, CloudWatch logs ~$1.50, S3 requests ~$0.30).

## Project Structure

```
generator/
    handler.py          # Lambda entry point
    sessions.py         # Session generation (CDR calls, SEQ browsing)
    generate.py         # Sessions -> records -> S3
    distribution.py     # Time-of-day traffic distribution
    phones.py           # 500K phone number pool
    towers.py           # Tower loading, adjacency, mobility
    websites.py         # 500 weighted domains
    reference/
        towers.json     # Static tower data (2000 entries)
scripts/
    gen_towers.py       # One-time tower reference generator
deploy/
    terraform/          # All infrastructure
```
