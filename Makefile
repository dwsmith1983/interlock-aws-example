.PHONY: build seed clean tf-bootstrap tf-init tf-plan tf-apply tf-destroy e2e kick \
       chaos-enable chaos-disable chaos-status chaos-report chaos-history

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

# Invoke both ingestion Lambdas immediately (run after seed to bootstrap first data)
kick:
	@echo "Invoking ingest-earthquake..."
	@aws lambda invoke --function-name $(TABLE_NAME)-ingest-earthquake --region $(REGION) --payload '{}' /dev/null --cli-read-timeout 120 --log-type Tail --query 'LogResult' --output text | base64 -d | tail -3
	@echo "Invoking ingest-crypto..."
	@aws lambda invoke --function-name $(TABLE_NAME)-ingest-crypto --region $(REGION) --payload '{}' /dev/null --cli-read-timeout 120 --log-type Tail --query 'LogResult' --output text | base64 -d | tail -3

# Run E2E tests
e2e:
	e2e/e2e-test.sh

# --- Chaos Testing ---

# Enable chaos testing (writes CHAOS#CONFIG with enabled=true)
chaos-enable:
	@echo "Enabling chaos testing (severity=$(SEVERITY))..."
	@aws dynamodb update-item \
		--table-name $(TABLE_NAME) \
		--region $(REGION) \
		--key '{"PK":{"S":"CHAOS#CONFIG"},"SK":{"S":"CURRENT"}}' \
		--update-expression "SET #d = :data" \
		--expression-attribute-names '{"#d":"data"}' \
		--expression-attribute-values "{\":data\":{\"S\":\"{\\\"enabled\\\":true,\\\"severity\\\":\\\"$(SEVERITY)\\\"}\"}}" \
		>/dev/null
	@echo "Chaos enabled with severity=$(SEVERITY)"

# Disable chaos testing (immediate kill switch)
chaos-disable:
	@echo "Disabling chaos testing..."
	@aws dynamodb update-item \
		--table-name $(TABLE_NAME) \
		--region $(REGION) \
		--key '{"PK":{"S":"CHAOS#CONFIG"},"SK":{"S":"CURRENT"}}' \
		--update-expression "SET #d = :data" \
		--expression-attribute-names '{"#d":"data"}' \
		--expression-attribute-values '{":data":{"S":"{\"enabled\":false}"}}' \
		>/dev/null
	@echo "Chaos disabled"

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

clean:
	rm -rf deploy/dist deploy/terraform/.build deploy/terraform/.terraform
