package main

import (
	"context"
	"log"
	"os"
	"time"

	"github.com/aws/aws-lambda-go/lambda"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/s3"

	chaosaws "github.com/dwsmith1983/chaos-data/adapters/aws"
	"github.com/dwsmith1983/chaos-data/pkg/types"

	"github.com/dwsmith1983/interlock-chaos/internal/handler"
)

func main() {
	cfg, err := awsconfig.LoadDefaultConfig(context.Background())
	if err != nil {
		log.Fatalf("load AWS config: %v", err)
	}

	s3Client := s3.NewFromConfig(cfg)
	dynamoClient := dynamodb.NewFromConfig(cfg)

	bucket := requireEnv("S3_BUCKET")
	prefix := envOrDefault("SCENARIO_PREFIX", "chaos/scenarios/")
	controlTable := requireEnv("INTERLOCK_CONTROL_TABLE")
	eventsTable := requireEnv("INTERLOCK_EVENTS_TABLE")
	maxSevStr := envOrDefault("MAX_SEVERITY", "moderate")

	maxSev, err := types.ParseSeverity(maxSevStr)
	if err != nil {
		log.Fatalf("parse MAX_SEVERITY: %v", err)
	}

	// Build AWS adapters.
	awsCfg := chaosaws.Config{
		StagingBucket:  bucket,
		PipelineBucket: bucket,
		TableName:      controlTable,
	}
	awsCfg.Defaults()

	transport := chaosaws.NewS3Transport(s3Client, awsCfg)
	emitter, err := chaosaws.NewDynamoDBEmitter(dynamoClient, eventsTable)
	if err != nil {
		log.Fatalf("create emitter: %v", err)
	}
	controlState := chaosaws.NewDynamoDBState(dynamoClient, controlTable)
	safety := chaosaws.NewDynamoDBSafety(dynamoClient, controlTable, 5*time.Minute)
	resolver := chaosaws.NewDynamoDBDependencyResolver(dynamoClient, controlTable)

	h := handler.New(handler.Config{
		S3Fetcher:   handler.NewS3Client(s3Client),
		Transport:   transport,
		Emitter:     emitter,
		SensorStore: controlState,
		SafetyCtrl:  safety,
		Resolver:    resolver,
		Bucket:      bucket,
		Prefix:      prefix,
		MaxSeverity: maxSev,
	})

	lambda.Start(h.Handle)
}

func requireEnv(key string) string {
	val := os.Getenv(key)
	if val == "" {
		log.Fatalf("required environment variable %s is not set", key)
	}
	return val
}

func envOrDefault(key, fallback string) string {
	val := os.Getenv(key)
	if val == "" {
		return fallback
	}
	return val
}
