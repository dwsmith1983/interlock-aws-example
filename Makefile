.PHONY: build seed clean tf-bootstrap tf-init tf-plan tf-apply tf-destroy e2e kick \
       chaos-enable chaos-disable chaos-status chaos-report chaos-history \
       fresh-start nuke dashboard-build dashboard-deploy retrigger

BUCKET_NAME ?= $(shell aws sts get-caller-identity --query Account --output text | xargs -I{} echo "$(TABLE_NAME)-data-{}")
TABLE_NAME  ?= medallion-interlock
REGION      ?= ap-southeast-1
SEVERITY    ?= moderate

# Build all Go Lambda binaries + stage archetype layer
build:
	deploy/build.sh

# Register pipelines into DynamoDB
seed:
	go run ./cmd/seed \
		--table $(TABLE_NAME) \
		--region $(REGION) \
		--bucket $(BUCKET_NAME) \
		--pipelines pipelines \
		--chaos-config chaos/scenarios.yaml

# Bootstrap Terraform state backend (run once)
tf-bootstrap:
	cd deploy/terraform/bootstrap && terraform init && terraform apply

# Initialize Terraform
tf-init:
	cd deploy/terraform && terraform init

# Plan Terraform changes
tf-plan: build
	cd deploy/terraform && terraform plan

# Apply Terraform changes
tf-apply: build
	cd deploy/terraform && terraform apply

# Destroy all Terraform-managed resources
tf-destroy:
	cd deploy/terraform && terraform destroy

# Wipe S3 + destroy all resources
nuke:
	@echo "Emptying S3 bucket $(BUCKET_NAME)..."
	-@aws s3 rm s3://$(BUCKET_NAME)/ --recursive --region $(REGION) 2>/dev/null || true
	cd deploy/terraform && terraform destroy -auto-approve -var="chaos_enabled=true"

# Full clean deploy: nuke -> build -> deploy -> seed -> kick
CHAOS ?= true
fresh-start: build
	@echo "=== Fresh Start (chaos=$(CHAOS)) ==="
	-@aws s3 rm s3://$(BUCKET_NAME)/ --recursive --region $(REGION) 2>/dev/null || true
	-cd deploy/terraform && terraform destroy -auto-approve -var="chaos_enabled=$(CHAOS)" 2>/dev/null || true
	cd deploy/terraform && terraform apply -auto-approve -var="chaos_enabled=$(CHAOS)"
	$(MAKE) seed
	$(MAKE) kick
	@if [ "$(CHAOS)" = "true" ]; then $(MAKE) chaos-enable; fi
	@echo "=== Fresh Start complete ==="

# Invoke both ingestion Lambdas immediately (run after seed to bootstrap first data)
kick:
	@echo "Invoking ingest-earthquake..."
	@aws lambda invoke --function-name $(TABLE_NAME)-ingest-earthquake --region $(REGION) --payload '{}' /dev/null --cli-read-timeout 120 --log-type Tail --query 'LogResult' --output text | base64 -d | tail -3
	@echo "Invoking ingest-crypto..."
	@aws lambda invoke --function-name $(TABLE_NAME)-ingest-crypto --region $(REGION) --payload '{}' /dev/null --cli-read-timeout 120 --log-type Tail --query 'LogResult' --output text | base64 -d | tail -3

# Manually retrigger a pipeline (bypasses SFN execution name dedup)
# Usage: make retrigger PIPELINE=earthquake-gold SCHEDULE=h16 DATE=2026-02-27
STATE_MACHINE_ARN ?= $(shell cd deploy/terraform && terraform output -raw state_machine_arn 2>/dev/null)
retrigger:
	@aws stepfunctions start-execution \
		--state-machine-arn $(STATE_MACHINE_ARN) \
		--name "$(PIPELINE)_$(DATE)_$(SCHEDULE)_manual-$(shell date +%s)" \
		--input '{"pipelineID":"$(PIPELINE)","scheduleID":"$(SCHEDULE)","date":"$(DATE)"}' \
		--region $(REGION) \
		--query 'executionArn' --output text

# Run E2E tests
e2e:
	e2e/e2e-test.sh

# --- Chaos Testing ---

# Enable chaos testing (merges enabled/severity into existing config)
chaos-enable:
	@echo "Enabling chaos testing (severity=$(SEVERITY))..."
	@python3 -c "\
	import json, boto3, sys; \
	c = boto3.client('dynamodb', region_name='$(REGION)'); \
	r = c.get_item(TableName='$(TABLE_NAME)', Key={'PK':{'S':'CHAOS#CONFIG'},'SK':{'S':'CURRENT'}}); \
	d = json.loads(r.get('Item',{}).get('data',{}).get('S','{}')); \
	d['enabled'] = True; d['severity'] = '$(SEVERITY)'; \
	c.update_item(TableName='$(TABLE_NAME)', Key={'PK':{'S':'CHAOS#CONFIG'},'SK':{'S':'CURRENT'}}, \
	  UpdateExpression='SET #d = :data', ExpressionAttributeNames={'#d':'data'}, \
	  ExpressionAttributeValues={':data':{'S':json.dumps(d)}}); \
	print(f'Chaos enabled with severity=$(SEVERITY) ({len(d.get(\"scenarios\",[]))} scenarios)')"

# Disable chaos testing (immediate kill switch — preserves scenarios)
chaos-disable:
	@echo "Disabling chaos testing..."
	@python3 -c "\
	import json, boto3; \
	c = boto3.client('dynamodb', region_name='$(REGION)'); \
	r = c.get_item(TableName='$(TABLE_NAME)', Key={'PK':{'S':'CHAOS#CONFIG'},'SK':{'S':'CURRENT'}}); \
	d = json.loads(r.get('Item',{}).get('data',{}).get('S','{}')); \
	d['enabled'] = False; \
	c.update_item(TableName='$(TABLE_NAME)', Key={'PK':{'S':'CHAOS#CONFIG'},'SK':{'S':'CURRENT'}}, \
	  UpdateExpression='SET #d = :data', ExpressionAttributeNames={'#d':'data'}, \
	  ExpressionAttributeValues={':data':{'S':json.dumps(d)}}); \
	print('Chaos disabled')"

# Show chaos event status summary
chaos-status:
	@echo "=== Chaos Events ==="
	@aws dynamodb query \
		--table-name $(TABLE_NAME) \
		--region $(REGION) \
		--key-condition-expression "PK = :pk" \
		--expression-attribute-values '{":pk":{"S":"CHAOS#EVENTS"}}' \
		--query 'Items[].{scenario:scenario.S,target:target.S,status:status.S,injectedAt:injectedAt.S}' \
		--output table 2>/dev/null || echo "No chaos events found"

# Summary report: counts by status
chaos-report:
	@echo "=== Chaos Report ==="
	@aws dynamodb query \
		--table-name $(TABLE_NAME) \
		--region $(REGION) \
		--key-condition-expression "PK = :pk" \
		--expression-attribute-values '{":pk":{"S":"CHAOS#EVENTS"}}' \
		--query 'Items[].status.S' \
		--output text 2>/dev/null | tr '\t' '\n' | sort | uniq -c | sort -rn || echo "No chaos events found"

# Full timeline of chaos events
chaos-history:
	@echo "=== Chaos History ==="
	@aws dynamodb query \
		--table-name $(TABLE_NAME) \
		--region $(REGION) \
		--key-condition-expression "PK = :pk" \
		--expression-attribute-values '{":pk":{"S":"CHAOS#EVENTS"}}' \
		--scan-index-forward \
		--query 'Items[].{time:injectedAt.S,scenario:scenario.S,target:target.S,status:status.S,category:category.S}' \
		--output table 2>/dev/null || echo "No chaos events found"

# --- Dashboard ---

DASHBOARD_BUCKET ?= $(shell cd deploy/terraform && terraform output -raw dashboard_bucket 2>/dev/null)
API_URL          ?= $(shell cd deploy/terraform && terraform output -raw evaluator_api_url 2>/dev/null)

# Build the Next.js dashboard static export
dashboard-build:
	@echo "Building dashboard..."
	cd dashboard && npm install && NEXT_PUBLIC_API_URL=$(API_URL)/dashboard npm run build
	@echo "Dashboard built to dashboard/out/"

# Deploy static site to S3 and invalidate CloudFront
dashboard-deploy: dashboard-build
	@echo "Deploying dashboard to s3://$(DASHBOARD_BUCKET)..."
	aws s3 sync dashboard/out/ s3://$(DASHBOARD_BUCKET)/ --delete --region $(REGION)
	@echo "Dashboard deployed"

clean:
	rm -rf deploy/dist deploy/terraform/.build deploy/terraform/.terraform dashboard/out dashboard/.next
