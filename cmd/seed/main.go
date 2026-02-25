// seed registers all medallion pipeline configs into the interlock DynamoDB table
// with 24 hourly schedules (h00-h23) generated per pipeline. Also seeds CHAOS#CONFIG
// and CONTROL# records for observability.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/dwsmith1983/interlock/pkg/types"
	"gopkg.in/yaml.v3"
)

// pipelineFile is the on-disk YAML format (before schedule generation).
type pipelineFile struct {
	ID          string                 `yaml:"id"`
	Name        string                 `yaml:"name"`
	Description string                 `yaml:"description"`
	Archetype   string                 `yaml:"archetype"`
	Traits      []traitOverride        `yaml:"traits"`
	Trigger     *types.TriggerConfig   `yaml:"trigger"`
	SLA         *types.SLAConfig       `yaml:"sla"`
	Exclusions  *types.ExclusionConfig `yaml:"exclusions"`
}

type traitOverride struct {
	Type      string                 `yaml:"type"`
	Evaluator string                 `yaml:"evaluator"`
	Config    map[string]interface{} `yaml:"config"`
}

// chaosConfig is the on-disk YAML format for chaos scenarios.
type chaosConfig struct {
	Enabled   bool                     `yaml:"enabled"`
	Severity  string                   `yaml:"severity"`
	Scenarios []map[string]interface{} `yaml:"scenarios"`
}

func generateHourlySchedules() []types.ScheduleConfig {
	schedules := make([]types.ScheduleConfig, 24)
	for h := 0; h < 24; h++ {
		schedules[h] = types.ScheduleConfig{
			Name:     fmt.Sprintf("h%02d", h),
			After:    fmt.Sprintf("%02d:10", h),
			Deadline: fmt.Sprintf("%02d:50", h),
			Timezone: "UTC",
		}
	}
	return schedules
}

func loadPipeline(path string) (*pipelineFile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading %s: %w", path, err)
	}
	var pf pipelineFile
	if err := yaml.Unmarshal(data, &pf); err != nil {
		return nil, fmt.Errorf("parsing %s: %w", path, err)
	}
	return &pf, nil
}

func buildConfig(pf *pipelineFile, bucketName, tableName string) types.PipelineConfig {
	traits := make(map[string]types.TraitConfig, len(pf.Traits))
	for _, t := range pf.Traits {
		cfg := make(map[string]interface{}, len(t.Config))
		for k, v := range t.Config {
			s, ok := v.(string)
			if ok {
				s = strings.ReplaceAll(s, "${BUCKET_NAME}", bucketName)
				s = strings.ReplaceAll(s, "${TABLE_NAME}", tableName)
				cfg[k] = s
			} else {
				cfg[k] = v
			}
		}
		traits[t.Type] = types.TraitConfig{Evaluator: t.Evaluator, Config: cfg}
	}

	// Resolve template variables in trigger arguments.
	if pf.Trigger != nil && len(pf.Trigger.Arguments) > 0 {
		for k, v := range pf.Trigger.Arguments {
			v = strings.ReplaceAll(v, "${BUCKET_NAME}", bucketName)
			v = strings.ReplaceAll(v, "${TABLE_NAME}", tableName)
			pf.Trigger.Arguments[k] = v
		}
	}

	return types.PipelineConfig{
		Name:       pf.ID,
		Archetype:  pf.Archetype,
		Traits:     traits,
		Trigger:    pf.Trigger,
		SLA:        pf.SLA,
		Schedules:  generateHourlySchedules(),
		Exclusions: pf.Exclusions,
	}
}

func registerPipeline(ctx context.Context, client *dynamodb.Client, tableName string, cfg types.PipelineConfig) error {
	data, err := json.Marshal(cfg)
	if err != nil {
		return fmt.Errorf("marshaling pipeline: %w", err)
	}

	pk := "PIPELINE#" + cfg.Name
	_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: &tableName,
		Item: map[string]ddbtypes.AttributeValue{
			"PK":     &ddbtypes.AttributeValueMemberS{Value: pk},
			"SK":     &ddbtypes.AttributeValueMemberS{Value: "CONFIG"},
			"GSI1PK": &ddbtypes.AttributeValueMemberS{Value: "TYPE#pipeline"},
			"GSI1SK": &ddbtypes.AttributeValueMemberS{Value: pk},
			"data":   &ddbtypes.AttributeValueMemberS{Value: string(data)},
		},
	})
	return err
}

func seedChaosConfig(ctx context.Context, client *dynamodb.Client, tableName, chaosPath string) error {
	data, err := os.ReadFile(chaosPath)
	if err != nil {
		if os.IsNotExist(err) {
			fmt.Println("no chaos config found, skipping CHAOS#CONFIG seed")
			return nil
		}
		return fmt.Errorf("reading chaos config: %w", err)
	}

	var cc chaosConfig
	if err := yaml.Unmarshal(data, &cc); err != nil {
		return fmt.Errorf("parsing chaos config: %w", err)
	}

	jsonData, err := json.Marshal(cc)
	if err != nil {
		return fmt.Errorf("marshaling chaos config: %w", err)
	}

	_, err = client.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: &tableName,
		Item: map[string]ddbtypes.AttributeValue{
			"PK":     &ddbtypes.AttributeValueMemberS{Value: "CHAOS#CONFIG"},
			"SK":     &ddbtypes.AttributeValueMemberS{Value: "CURRENT"},
			"GSI1PK": &ddbtypes.AttributeValueMemberS{Value: "CHAOS"},
			"GSI1SK": &ddbtypes.AttributeValueMemberS{Value: "CONFIG"},
			"data":   &ddbtypes.AttributeValueMemberS{Value: string(jsonData)},
		},
	})
	return err
}

func seedControlRecord(ctx context.Context, client *dynamodb.Client, tableName, pipelineID string) error {
	pk := "CONTROL#" + pipelineID
	_, err := client.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: &tableName,
		Item: map[string]ddbtypes.AttributeValue{
			"PK":                   &ddbtypes.AttributeValueMemberS{Value: pk},
			"SK":                   &ddbtypes.AttributeValueMemberS{Value: "STATUS"},
			"GSI1PK":               &ddbtypes.AttributeValueMemberS{Value: "CONTROLS"},
			"GSI1SK":               &ddbtypes.AttributeValueMemberS{Value: pipelineID},
			"enabled":              &ddbtypes.AttributeValueMemberBOOL{Value: true},
			"consecutiveFailures":  &ddbtypes.AttributeValueMemberN{Value: "0"},
			"chaosActive":          &ddbtypes.AttributeValueMemberBOOL{Value: false},
		},
	})
	return err
}

func main() {
	tableName := flag.String("table", "medallion-interlock", "DynamoDB table name")
	region := flag.String("region", "us-east-1", "AWS region")
	bucketName := flag.String("bucket", "", "S3 data bucket name (required)")
	pipelineDir := flag.String("pipelines", "pipelines", "Directory containing pipeline YAML files")
	chaosPath := flag.String("chaos-config", "chaos/scenarios.yaml", "Path to chaos scenarios YAML")
	flag.Parse()

	if *bucketName == "" {
		log.Fatal("--bucket is required")
	}

	awsCfg, err := awsconfig.LoadDefaultConfig(context.Background(),
		awsconfig.WithRegion(*region),
	)
	if err != nil {
		log.Fatalf("loading AWS config: %v", err)
	}
	client := dynamodb.NewFromConfig(awsCfg)

	files, err := filepath.Glob(filepath.Join(*pipelineDir, "*.yaml"))
	if err != nil {
		log.Fatalf("listing pipeline files: %v", err)
	}
	if len(files) == 0 {
		log.Fatalf("no pipeline YAML files found in %s", *pipelineDir)
	}

	ctx := context.Background()
	for _, f := range files {
		pf, err := loadPipeline(f)
		if err != nil {
			log.Fatalf("loading pipeline: %v", err)
		}

		cfg := buildConfig(pf, *bucketName, *tableName)
		if err := registerPipeline(ctx, client, *tableName, cfg); err != nil {
			log.Fatalf("registering pipeline %s: %v", pf.ID, err)
		}

		// Seed CONTROL# record
		if err := seedControlRecord(ctx, client, *tableName, pf.ID); err != nil {
			log.Fatalf("seeding CONTROL record for %s: %v", pf.ID, err)
		}

		fmt.Printf("registered pipeline %s (%s) with %d schedules\n", pf.ID, pf.Name, len(cfg.Schedules))
	}
	fmt.Printf("\nsuccessfully registered %d pipelines\n", len(files))

	// Seed chaos config
	if err := seedChaosConfig(ctx, client, *tableName, *chaosPath); err != nil {
		log.Fatalf("seeding chaos config: %v", err)
	}
	fmt.Println("seeded CHAOS#CONFIG record")
}
