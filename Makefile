.PHONY: build-generator tf-init tf-apply tf-destroy clean

GENERATOR_DIR := generator
BUILD_DIR := build
DEPLOY_DIR := deploy/terraform

build-generator:
	@echo "Packaging telecom-generator Lambda..."
	@mkdir -p $(BUILD_DIR)
	@cd $(GENERATOR_DIR) && zip -r ../$(BUILD_DIR)/telecom-generator.zip . -x '__pycache__/*' '*.pyc'
	@echo "Built $(BUILD_DIR)/telecom-generator.zip"

tf-init:
	cd $(DEPLOY_DIR) && terraform init

tf-apply:
	cd $(DEPLOY_DIR) && terraform apply

tf-destroy:
	cd $(DEPLOY_DIR) && terraform destroy

clean:
	rm -rf $(BUILD_DIR)
