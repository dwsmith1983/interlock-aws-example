.PHONY: build-generator build-bronze build-delta-layer build-ppf-wheel build-glue-jobs build-interlock build-audit upload-glue-scripts build-all tf-init tf-apply tf-destroy clean deploy restart-schedules

GENERATOR_DIR := generator
BRONZE_DIR := bronze_consumer
GLUE_DIR := glue_jobs
BUILD_DIR := build
DEPLOY_DIR := deploy/terraform
PPF_DIR := $(HOME)/code/pyspark-pipeline-framework
ENVIRONMENT := dev
AWS_REGION := ap-southeast-1

build-generator:
	@echo "Packaging telecom-generator Lambda..."
	@mkdir -p $(BUILD_DIR)
	@zip -r $(BUILD_DIR)/telecom-generator.zip $(GENERATOR_DIR) -x '$(GENERATOR_DIR)/__pycache__/*' '*.pyc'
	@echo "Built $(BUILD_DIR)/telecom-generator.zip"

build-bronze:
	@echo "Packaging bronze-consumer Lambda..."
	@mkdir -p $(BUILD_DIR)
	@zip -r $(BUILD_DIR)/bronze-consumer.zip $(BRONZE_DIR) -x '$(BRONZE_DIR)/__pycache__/*' '*.pyc'
	@echo "Built $(BUILD_DIR)/bronze-consumer.zip"

build-delta-layer:
	@echo "Building Delta Lake Lambda layer..."
	@scripts/build_delta_layer.sh

build-ppf-wheel:
	@echo "Building pyspark-pipeline-framework wheel..."
	@mkdir -p $(BUILD_DIR)
	@pip wheel --no-deps --wheel-dir $(BUILD_DIR) $(PPF_DIR)
	@mv $(BUILD_DIR)/pyspark_pipeline_framework-*.whl $(BUILD_DIR)/ppf.whl
	@echo "Built $(BUILD_DIR)/ppf.whl"

build-glue-jobs:
	@echo "Packaging glue_jobs module..."
	@mkdir -p $(BUILD_DIR)
	@zip -r $(BUILD_DIR)/glue_jobs.zip $(GLUE_DIR) -x '$(GLUE_DIR)/__pycache__/*' '*.pyc'
	@echo "Built $(BUILD_DIR)/glue_jobs.zip"

upload-glue-scripts:
	@echo "Uploading Glue scripts..."
	@$(eval BUCKET := $(shell cd $(DEPLOY_DIR) && terraform output -raw telecom_data_bucket))
	aws s3 sync $(GLUE_DIR)/ s3://$(BUCKET)/glue_scripts/glue_jobs/ --exclude '__pycache__/*' --exclude '*.pyc'
	@echo "Uploaded to s3://$(BUCKET)/glue_scripts/"

build-interlock:
	@echo "Building Interlock Lambda binaries..."
	@scripts/build_interlock.sh

build-audit:
	@echo "Packaging bronze-audit Lambda..."
	@mkdir -p $(BUILD_DIR)
	@zip -r $(BUILD_DIR)/bronze-audit.zip audit -x 'audit/__pycache__/*' '*.pyc'
	@echo "Built $(BUILD_DIR)/bronze-audit.zip"

build-all: build-generator build-bronze build-ppf-wheel build-glue-jobs build-interlock build-audit
	@echo "All build artifacts ready in $(BUILD_DIR)/"

tf-init:
	cd $(DEPLOY_DIR) && terraform init

tf-apply:
	cd $(DEPLOY_DIR) && terraform apply

tf-destroy:
	cd $(DEPLOY_DIR) && terraform destroy

restart-schedules:
	@echo "Cycling EventBridge schedules..."
	@aws events disable-rule --name $(ENVIRONMENT)-telecom-cdr-schedule --region $(AWS_REGION)
	@aws events disable-rule --name $(ENVIRONMENT)-telecom-seq-schedule --region $(AWS_REGION)
	@sleep 2
	@aws events enable-rule --name $(ENVIRONMENT)-telecom-cdr-schedule --region $(AWS_REGION)
	@aws events enable-rule --name $(ENVIRONMENT)-telecom-seq-schedule --region $(AWS_REGION)
	@echo "EventBridge schedules restarted"

deploy: tf-apply restart-schedules
	@echo "Deploy complete — schedules are active"

clean:
	rm -rf $(BUILD_DIR)
