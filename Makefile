.PHONY: build seed clean tf-bootstrap tf-init tf-plan tf-apply tf-destroy e2e

BUCKET_NAME ?= $(shell aws sts get-caller-identity --query Account --output text | xargs -I{} echo "$(TABLE_NAME)-data-{}")
TABLE_NAME  ?= medallion-interlock
REGION      ?= ap-southeast-1

# Build all Go Lambda binaries + stage archetype layer
build:
	deploy/build.sh

# Register pipelines into DynamoDB
seed:
	go run ./cmd/seed \
		--table $(TABLE_NAME) \
		--region $(REGION) \
		--bucket $(BUCKET_NAME) \
		--pipelines pipelines

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
	@echo "Invoking ingest-gharchive..."
	@aws lambda invoke --function-name $(TABLE_NAME)-ingest-gharchive --region $(REGION) --payload '{}' /dev/null --cli-read-timeout 300 --log-type Tail --query 'LogResult' --output text | base64 -d | tail -3
	@echo "Invoking ingest-openmeteo..."
	@aws lambda invoke --function-name $(TABLE_NAME)-ingest-openmeteo --region $(REGION) --payload '{}' /dev/null --cli-read-timeout 120 --log-type Tail --query 'LogResult' --output text | base64 -d | tail -3

# Run E2E tests
e2e:
	e2e/e2e-test.sh

clean:
	rm -rf deploy/dist deploy/terraform/.build deploy/terraform/.terraform
