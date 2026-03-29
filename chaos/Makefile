.PHONY: build chaos-enable chaos-disable chaos-status chaos-inject chaos-sync chaos-escalate test

ENVIRONMENT := dev
AWS_REGION := ap-southeast-1
BUILD_DIR := ../build/chaos
DEPLOY_DIR := terraform
S3_BUCKET := $(shell cd $(DEPLOY_DIR) && terraform output -raw s3_bucket_name 2>/dev/null || echo "BUCKET_NOT_SET")
FUNCTION_NAME := $(ENVIRONMENT)-chaos-controller
RULE_NAME := $(ENVIRONMENT)-chaos-schedule

build:
	@echo "Building chaos controller Lambda..."
	@scripts/build.sh
	@echo "Built $(BUILD_DIR)/chaos-controller.zip"

chaos-enable:
	@aws events enable-rule \
		--name $(RULE_NAME) \
		--region $(AWS_REGION)
	@echo "Chaos schedule ENABLED"

chaos-disable:
	@aws events disable-rule \
		--name $(RULE_NAME) \
		--region $(AWS_REGION)
	@echo "Chaos schedule DISABLED"

chaos-status:
	@aws events describe-rule \
		--name $(RULE_NAME) \
		--region $(AWS_REGION) \
		--query 'State' \
		--output text

chaos-inject:
	@test -n "$(SCENARIO)" || (echo "Usage: make chaos-inject SCENARIO=late-data-bronze" && exit 1)
	@aws lambda invoke \
		--function-name $(FUNCTION_NAME) \
		--payload '{"scenario":"$(SCENARIO)"}' \
		--region $(AWS_REGION) \
		--cli-binary-format raw-in-base64-out \
		/dev/stdout

chaos-escalate:
	@test -n "$(SEVERITY)" || (echo "Usage: make chaos-escalate SEVERITY=severe" && exit 1)
	@aws lambda update-function-configuration \
		--function-name $(FUNCTION_NAME) \
		--region $(AWS_REGION) \
		--environment "Variables={S3_BUCKET=$(S3_BUCKET),SCENARIO_PREFIX=chaos/scenarios/,INTERLOCK_CONTROL_TABLE=$(shell cd $(DEPLOY_DIR) && terraform output -raw interlock_control_table_name),INTERLOCK_EVENTS_TABLE=$(shell cd $(DEPLOY_DIR) && terraform output -raw interlock_events_table_name),MAX_SEVERITY=$(SEVERITY)}"
	@echo "Chaos max severity escalated to $(SEVERITY)"

chaos-sync:
	@aws s3 sync scenarios/ s3://$(S3_BUCKET)/chaos/scenarios/ \
		--region $(AWS_REGION) \
		--delete
	@echo "Scenarios synced to s3://$(S3_BUCKET)/chaos/scenarios/"

test:
	@cd .. && cd chaos && go test -race ./...
